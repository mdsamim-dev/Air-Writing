"""
╔══════════════════════════════════════════════════════════════════════╗
║       🔴 RED LASER AIR WRITING — Iron Man Cyberpunk Edition v2       ║
║       Draw glowing red energy in the air with your index finger      ║
╚══════════════════════════════════════════════════════════════════════╝

CONTROLS:
  ☝️  One finger up    → Draw mode  (red laser trail + sparks + particles)
  🖐️  Open palm        → Clear canvas instantly
  🤌  Pinch            → Select & move your drawing
  Q / ESC             → Quit

SETUP:
  pip install -r requirements.txt
  python main.py
"""

import cv2
import numpy as np
import mediapipe as mp
from collections import deque
import time
import random
import math

# ════════════════════════════════════════════════
#  ⚙️  CONFIGURATION  — tune to your taste
# ════════════════════════════════════════════════

# Camera
CAM_WIDTH          = 1280
CAM_HEIGHT         = 720

# Drawing feel
SMOOTHING_WINDOW   = 7      # Rolling average window for finger position (higher = smoother)
MIN_DRAW_DISTANCE  = 3      # Minimum pixels to move before adding a point
INTERPOLATE_STEPS  = 6      # Sub-steps between consecutive points (fills gaps)

# Neon line visuals  (BGR color format)
CORE_COLOR         = (80,  80,  255)   # Bright red core
MID_GLOW_COLOR     = (40,  30,  200)   # Medium red glow
OUTER_GLOW_COLOR   = (20,  10,  120)   # Wide outer bloom
LINE_THICKNESS     = 3                  # Core line pixel width
GLOW_LAYERS        = 4                  # Blur passes (more = richer glow, slightly slower)

# Particle / spark system
MAX_PARTICLES      = 280    # Maximum live particles at once
SPARKS_PER_FRAME   = 6      # New sparks spawned every draw frame
PARTICLE_LIFETIME  = 22     # Frames a spark lives

# Gesture thresholds
PINCH_THRESHOLD    = 0.07   # Normalized thumb-index distance for pinch
SELECT_RADIUS      = 80     # How close (px) you need to pinch to grab a stroke
PALM_THRESHOLD     = 4      # Fingers-up count that triggers palm-clear (4 or 5)

# ════════════════════════════════════════════════
#  MediaPipe landmark indices
# ════════════════════════════════════════════════
mp_hands   = mp.solutions.hands
mp_drawing = mp.solutions.drawing_utils

TIP_INDEX  = 8    # Index fingertip
TIP_MIDDLE = 12
TIP_RING   = 16
TIP_PINKY  = 20
TIP_THUMB  = 4
MCP_THUMB  = 2    # Thumb base knuckle


# ════════════════════════════════════════════════
#  🖐  GESTURE HELPERS
# ════════════════════════════════════════════════

def count_fingers_up(lm, handedness="Right"):
    """Count how many fingers (including thumb) are extended."""
    tips = [TIP_INDEX, TIP_MIDDLE, TIP_RING, TIP_PINKY]
    pips = [6, 10, 14, 18]   # PIP joint = one joint below each tip

    # A finger is "up" when its tip is above its PIP joint (lower y = higher on screen)
    count = sum(1 for tip, pip in zip(tips, pips) if lm[tip].y < lm[pip].y)

    # Thumb uses x-axis (mirrored for left hand)
    if handedness == "Right":
        if lm[TIP_THUMB].x < lm[MCP_THUMB].x:
            count += 1
    else:
        if lm[TIP_THUMB].x > lm[MCP_THUMB].x:
            count += 1

    return count


def is_pinching(lm):
    """True when thumb tip and index tip are very close together."""
    dist = math.hypot(lm[TIP_THUMB].x - lm[TIP_INDEX].x,
                      lm[TIP_THUMB].y - lm[TIP_INDEX].y)
    return dist < PINCH_THRESHOLD


# ════════════════════════════════════════════════
#  ✨  PARTICLE SYSTEM
# ════════════════════════════════════════════════

class Particle:
    """
    A single glowing spark or smoke puff that flies away from the
    fingertip while drawing. Each particle has its own position,
    velocity, color, size, and remaining lifetime.
    """
    __slots__ = ("x", "y", "vx", "vy", "life", "max_life",
                 "size", "color", "kind")

    def __init__(self, x, y, kind="spark"):
        self.x        = float(x)
        self.y        = float(y)
        self.kind     = kind
        self.max_life = PARTICLE_LIFETIME + random.randint(-6, 8)
        self.life     = self.max_life

        if kind == "spark":
            # Fast sparks that shoot outward in random directions
            angle     = random.uniform(0, math.tau)
            speed     = random.uniform(2.5, 7.0)
            self.vx   = math.cos(angle) * speed
            self.vy   = math.sin(angle) * speed
            self.size = random.uniform(1.5, 3.5)
            # Red-to-orange color range
            r, g, b   = 255, random.randint(0, 80), random.randint(0, 30)
            self.color = (b, g, r)   # BGR

        else:  # smoke / aura puff
            angle     = random.uniform(0, math.tau)
            speed     = random.uniform(0.4, 1.5)
            self.vx   = math.cos(angle) * speed
            self.vy   = math.sin(angle) * speed - 0.5   # drift upward
            self.size = random.uniform(6.0, 18.0)
            self.color = (20, 10, random.randint(80, 140))   # dim red smoke

    def update(self):
        """Advance physics by one frame. Returns False when particle should die."""
        self.x   += self.vx
        self.y   += self.vy
        self.vy  += 0.12   # gravity
        self.vx  *= 0.94   # drag
        self.life -= 1
        return self.life > 0

    @property
    def alpha(self):
        """Fade factor 1→0 over lifetime."""
        return self.life / self.max_life


def spawn_particles(particles, x, y):
    """Spawn a burst of sparks + smoke at position (x, y)."""
    budget   = MAX_PARTICLES - len(particles)
    n_sparks = min(SPARKS_PER_FRAME, budget)
    n_smoke  = min(2, budget - n_sparks)
    for _ in range(n_sparks):
        particles.append(Particle(x, y, "spark"))
    for _ in range(n_smoke):
        particles.append(Particle(x, y, "smoke"))


def render_particles(canvas, particles):
    """Draw all live particles onto the canvas using additive blending."""
    if not particles:
        return

    layer = np.zeros_like(canvas)

    for p in particles:
        cx, cy = int(p.x), int(p.y)
        if not (0 <= cx < canvas.shape[1] and 0 <= cy < canvas.shape[0]):
            continue

        t = p.alpha   # fade factor

        if p.kind == "spark":
            radius = max(1, int(p.size * t))
            # Soft outer glow
            glow_c = tuple(int(c * t * 0.5) for c in p.color)
            cv2.circle(layer, (cx, cy), radius + 3, glow_c, -1, cv2.LINE_AA)
            # Bright core
            core_c = tuple(min(255, int(c * t)) for c in p.color)
            cv2.circle(layer, (cx, cy), radius, core_c, -1, cv2.LINE_AA)

        else:  # smoke puff — large, dim, expanding circle
            radius  = max(2, int(p.size * (1.2 - t * 0.5)))
            smoke_c = tuple(int(c * t * 0.35) for c in p.color)
            cv2.circle(layer, (cx, cy), radius, smoke_c, -1, cv2.LINE_AA)

    # Blur the whole particle layer for a glowing soft look
    blurred = cv2.GaussianBlur(layer, (9, 9), 0)
    cv2.add(canvas, blurred, canvas)


# ════════════════════════════════════════════════
#  🔴  NEON LINE RENDERER
# ════════════════════════════════════════════════

def interpolate_points(pts, steps=INTERPOLATE_STEPS):
    """
    Insert linearly-interpolated sub-points between each consecutive pair.
    This smooths out the line when MediaPipe tracking is sparse.
    """
    if len(pts) < 2:
        return list(pts)

    result = []
    for i in range(len(pts) - 1):
        x0, y0 = pts[i]
        x1, y1 = pts[i + 1]
        for t in range(steps):
            f = t / steps
            result.append((int(x0 + (x1 - x0) * f),
                            int(y0 + (y1 - y0) * f)))
    result.append(pts[-1])
    return result


def draw_neon_stroke(canvas, points):
    """
    Render a stroke as a red laser with layered Gaussian-blur glow.

    Layer stack (rendered bottom to top):
      1. Wide outer bloom  — large blur, very dim red
      2. Outer-mid glow    — medium-large blur
      3. Mid glow          — medium blur, brighter
      4. Inner glow        — tight blur, near-core brightness
      5. Bright red core   — sharp crisp line
      6. White-hot center  — 1px highlight for laser realism
    """
    if len(points) < 2:
        return

    pts = interpolate_points(points)

    # Each tuple: (color BGR, extra thickness, blur kernel size, blend alpha)
    glow_configs = [
        (OUTER_GLOW_COLOR, 14, 31, 0.40),
        (OUTER_GLOW_COLOR,  9, 19, 0.50),
        (MID_GLOW_COLOR,    6, 11, 0.55),
        (CORE_COLOR,        3,  7, 0.70),
    ]

    for color, thick_add, ksize, alpha in glow_configs:
        layer = np.zeros_like(canvas)
        thick = LINE_THICKNESS + thick_add
        for j in range(1, len(pts)):
            cv2.line(layer, pts[j-1], pts[j], color, thick, cv2.LINE_AA)
        k       = ksize if ksize % 2 == 1 else ksize + 1   # kernel must be odd
        blurred = cv2.GaussianBlur(layer, (k, k), 0)
        cv2.addWeighted(canvas, 1.0, blurred, alpha, 0, canvas)

    # Bright red core (sharp)
    for j in range(1, len(pts)):
        cv2.line(canvas, pts[j-1], pts[j], CORE_COLOR, LINE_THICKNESS, cv2.LINE_AA)

    # White-hot 1px laser center highlight
    for j in range(1, len(pts)):
        cv2.line(canvas, pts[j-1], pts[j], (200, 200, 255), 1, cv2.LINE_AA)


# ════════════════════════════════════════════════
#  🔵  ANIMATED FINGER CURSOR
# ════════════════════════════════════════════════

def draw_finger_cursor(frame, pt, tick):
    """
    Pulsing Iron-Man style targeting ring around the fingertip.
    'tick' drives the sine-wave pulse animation.
    """
    x, y  = pt
    pulse = abs(math.sin(tick * 0.18))
    r_in  = int(10 + pulse * 4)
    r_out = int(20 + pulse * 8)

    cv2.circle(frame, (x, y), r_out,      (20, 10, 100),  2, cv2.LINE_AA)  # outer ring
    cv2.circle(frame, (x, y), r_in + 3,   (50, 30, 200),  2, cv2.LINE_AA)  # mid ring
    cv2.circle(frame, (x, y), r_in,       (80, 60, 255), -1, cv2.LINE_AA)  # filled core
    cv2.circle(frame, (x, y), max(1, r_in - 5), (200, 190, 255), -1, cv2.LINE_AA)  # white center

    # Cross-hair arms
    arm     = r_out + 6
    dim_red = (30, 20, 140)
    cv2.line(frame, (x - arm, y),     (x - r_out - 2, y), dim_red, 1, cv2.LINE_AA)
    cv2.line(frame, (x + r_out + 2, y), (x + arm, y),     dim_red, 1, cv2.LINE_AA)
    cv2.line(frame, (x, y - arm),     (x, y - r_out - 2), dim_red, 1, cv2.LINE_AA)
    cv2.line(frame, (x, y + r_out + 2), (x, y + arm),     dim_red, 1, cv2.LINE_AA)


# ════════════════════════════════════════════════
#  🖥️  CYBERPUNK HUD
# ════════════════════════════════════════════════

def draw_hud(frame, mode, fps, selected, palm_flash):
    """Top bar, bottom hints, corner brackets, palm-clear flash overlay."""
    h, w = frame.shape[:2]

    # ── Top bar ─────────────────────────────────────────────
    ov = frame.copy()
    cv2.rectangle(ov, (0, 0), (w, 58), (0, 0, 0), -1)
    cv2.addWeighted(ov, 0.6, frame, 0.4, 0, frame)
    cv2.line(frame, (0, 58), (w, 58), (20, 10, 160), 1)
    cv2.line(frame, (0, 60), (w, 60), (8,  4,  60),  1)

    mode_colors = {
        "DRAW":   (60,  80, 255),
        "CLEAR":  (0,   60, 255),
        "SELECT": (0,  200, 255),
        "IDLE":   (60,  60,  80),
    }
    mc = mode_colors.get(mode, (60, 60, 80))
    cv2.putText(frame, f"[ {mode} MODE ]",
                (20, 40), cv2.FONT_HERSHEY_SIMPLEX, 0.85, mc, 2, cv2.LINE_AA)
    cv2.putText(frame, f"FPS {fps:03.0f}",
                (w - 130, 40), cv2.FONT_HERSHEY_SIMPLEX, 0.7,
                (40, 30, 180), 2, cv2.LINE_AA)
    if selected:
        cv2.putText(frame, "● MOVING",
                    (w // 2 - 55, 40), cv2.FONT_HERSHEY_SIMPLEX,
                    0.65, (0, 200, 255), 2, cv2.LINE_AA)

    # ── Bottom hint bar ──────────────────────────────────────
    ov2 = frame.copy()
    cv2.rectangle(ov2, (0, h - 36), (w, h), (0, 0, 0), -1)
    cv2.addWeighted(ov2, 0.55, frame, 0.45, 0, frame)
    cv2.line(frame, (0, h - 36), (w, h - 36), (8, 4, 60), 1)
    cv2.putText(frame, "☝ DRAW    OPEN PALM CLEAR    PINCH MOVE    Q QUIT",
                (20, h - 12), cv2.FONT_HERSHEY_SIMPLEX,
                0.5, (40, 30, 130), 1, cv2.LINE_AA)

    # ── Corner brackets ──────────────────────────────────────
    col, arm = (40, 25, 180), 20
    def bracket(x, y, dx, dy):
        cv2.line(frame, (x, y), (x + dx * arm, y), col, 2)
        cv2.line(frame, (x, y), (x, y + dy * arm), col, 2)
    bracket(10,      63,      1,  1)
    bracket(w - 10,  63,     -1,  1)
    bracket(10,      h - 40,  1, -1)
    bracket(w - 10,  h - 40, -1, -1)

    # ── Palm-clear flash ─────────────────────────────────────
    if palm_flash > 0:
        alpha = palm_flash / 14.0 * 0.38
        flash = frame.copy()
        cv2.rectangle(flash, (0, 0), (w, h), (0, 0, 180), -1)
        cv2.addWeighted(flash, alpha, frame, 1 - alpha, 0, frame)
        if palm_flash > 7:
            cv2.putText(frame, "CANVAS CLEARED",
                        (w // 2 - 200, h // 2),
                        cv2.FONT_HERSHEY_SIMPLEX, 1.8,
                        (80, 60, 255), 4, cv2.LINE_AA)


# ════════════════════════════════════════════════
#  🚀  MAIN APPLICATION LOOP
# ════════════════════════════════════════════════

def main():
    print("\n🔴 Red Laser Air Writing System — Cyberpunk v2")
    print("   ☝  One finger  → Draw")
    print("   🖐  Open palm   → Clear canvas")
    print("   🤌  Pinch       → Move drawing")
    print("   Q / ESC        → Quit\n")

    # ── Webcam ──────────────────────────────────────────────
    cap = cv2.VideoCapture(0)
    cap.set(cv2.CAP_PROP_FRAME_WIDTH,  CAM_WIDTH)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, CAM_HEIGHT)
    cap.set(cv2.CAP_PROP_FPS, 60)

    if not cap.isOpened():
        print("❌  Camera not found. Check connection and try again.")
        return

    fw = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    fh = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    print(f"   Camera: {fw}×{fh}\n")

    # ── Persistent neon drawing canvas ──────────────────────
    canvas = np.zeros((fh, fw, 3), dtype=np.uint8)

    # ── Stroke storage ──────────────────────────────────────
    # strokes      : list of completed strokes, each stroke = list of (x,y) tuples
    # current_stroke: the stroke currently being drawn
    strokes: list[list[tuple[int, int]]] = []
    current_stroke: list[tuple[int, int]] = []

    # ── Particle system ─────────────────────────────────────
    particles: list[Particle] = []

    # ── Smoothing buffer ────────────────────────────────────
    # Rolling average of last SMOOTHING_WINDOW finger positions
    smooth_buf: deque = deque(maxlen=SMOOTHING_WINDOW)

    # ── State ────────────────────────────────────────────────
    mode          = "IDLE"
    prev_point    = None     # Last drawn point (for gap-distance check)
    selected_idx  = None     # Which stroke is currently grabbed (move mode)
    move_offset   = (0, 0)   # Offset from pinch point to stroke anchor
    last_pinch_pt = None
    palm_flash    = 0        # Countdown frames for palm-clear screen flash
    tick          = 0        # Global frame counter (drives cursor animation)

    # ── FPS ─────────────────────────────────────────────────
    fps     = 0.0
    t_prev  = time.time()
    f_count = 0

    # ── MediaPipe Hands ─────────────────────────────────────
    with mp_hands.Hands(
        static_image_mode        = False,
        max_num_hands            = 1,          # Only track one hand
        min_detection_confidence = 0.72,
        min_tracking_confidence  = 0.65,
    ) as hands:

        while True:
            ret, frame = cap.read()
            if not ret:
                continue

            frame  = cv2.flip(frame, 1)   # Mirror for natural selfie view
            tick  += 1

            # ── FPS ─────────────────────────────────────────
            f_count += 1
            t_now    = time.time()
            if t_now - t_prev >= 0.5:
                fps     = f_count / (t_now - t_prev)
                f_count = 0
                t_prev  = t_now

            # ── Hand tracking ────────────────────────────────
            rgb                  = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            rgb.flags.writeable  = False
            results              = hands.process(rgb)
            rgb.flags.writeable  = True

            mode = "IDLE"

            if results.multi_hand_landmarks:
                hand_lm    = results.multi_hand_landmarks[0]
                handedness = results.multi_handedness[0].classification[0].label
                lm         = hand_lm.landmark

                # ── Raw fingertip pixel position ────────────
                raw_x = int(lm[TIP_INDEX].x * fw)
                raw_y = int(lm[TIP_INDEX].y * fh)

                # ── Smoothed position (rolling average) ─────
                smooth_buf.append((raw_x, raw_y))
                sx        = int(np.mean([p[0] for p in smooth_buf]))
                sy        = int(np.mean([p[1] for p in smooth_buf]))
                smooth_pt = (sx, sy)

                # ── Gesture classification ───────────────────
                n_fingers = count_fingers_up(lm, handedness)
                pinching  = is_pinching(lm)

                # Priority: open palm > pinch > one finger
                if n_fingers >= PALM_THRESHOLD and not pinching:
                    mode = "CLEAR"
                elif pinching:
                    mode = "SELECT"
                elif n_fingers == 1:
                    mode = "DRAW"

                # ══════════════════════════
                #  ☝  DRAW
                # ══════════════════════════
                if mode == "DRAW":
                    selected_idx  = None
                    last_pinch_pt = None

                    if prev_point is not None:
                        dist = math.hypot(smooth_pt[0] - prev_point[0],
                                          smooth_pt[1] - prev_point[1])
                        if dist >= MIN_DRAW_DISTANCE:
                            current_stroke.append(smooth_pt)
                            # Emit sparks at the fingertip each frame
                            spawn_particles(particles, smooth_pt[0], smooth_pt[1])
                    else:
                        current_stroke = [smooth_pt]   # start fresh stroke

                    prev_point = smooth_pt
                    draw_finger_cursor(frame, smooth_pt, tick)

                # ══════════════════════════
                #  🖐  CLEAR (open palm)
                # ══════════════════════════
                elif mode == "CLEAR":
                    if current_stroke:
                        strokes.append(current_stroke)
                        current_stroke = []

                    strokes.clear()
                    canvas[:] = 0
                    particles.clear()
                    prev_point    = None
                    selected_idx  = None
                    smooth_buf.clear()
                    palm_flash    = 14   # trigger red flash overlay

                    cv2.putText(frame, "PALM — CLEARING",
                                (smooth_pt[0] - 110, smooth_pt[1] - 30),
                                cv2.FONT_HERSHEY_SIMPLEX, 0.7,
                                (60, 50, 255), 2, cv2.LINE_AA)

                # ══════════════════════════
                #  🤌  SELECT / MOVE
                # ══════════════════════════
                elif mode == "SELECT":
                    if current_stroke:
                        strokes.append(current_stroke[:])
                        current_stroke = []

                    # Pinch anchor = midpoint between thumb and index tips
                    tx       = int(lm[TIP_THUMB].x * fw)
                    ty       = int(lm[TIP_THUMB].y * fh)
                    pinch_pt = ((sx + tx) // 2, (sy + ty) // 2)

                    if selected_idx is None and last_pinch_pt is None:
                        # Find the nearest stroke within grab radius
                        best_i, best_d = None, float("inf")
                        for i, stroke in enumerate(strokes):
                            for pt in stroke:
                                d = math.hypot(pt[0] - pinch_pt[0],
                                               pt[1] - pinch_pt[1])
                                if d < best_d:
                                    best_d, best_i = d, i
                        if best_i is not None and best_d < SELECT_RADIUS:
                            selected_idx = best_i
                            anchor       = strokes[selected_idx][0]
                            move_offset  = (pinch_pt[0] - anchor[0],
                                            pinch_pt[1] - anchor[1])

                    # Translate the grabbed stroke by pinch delta
                    if selected_idx is not None and selected_idx < len(strokes):
                        new_ax = pinch_pt[0] - move_offset[0]
                        new_ay = pinch_pt[1] - move_offset[1]
                        old_ax, old_ay = strokes[selected_idx][0]
                        dx = new_ax - old_ax
                        dy = new_ay - old_ay
                        strokes[selected_idx] = [
                            (p[0] + dx, p[1] + dy)
                            for p in strokes[selected_idx]
                        ]
                        move_offset = (
                            pinch_pt[0] - strokes[selected_idx][0][0],
                            pinch_pt[1] - strokes[selected_idx][0][1],
                        )

                    last_pinch_pt = pinch_pt
                    prev_point    = None

                    # Pinch cursor visuals
                    cv2.circle(frame, pinch_pt, 12, (0, 200, 255), -1, cv2.LINE_AA)
                    cv2.circle(frame, pinch_pt, 20, (0, 160, 200),  2, cv2.LINE_AA)
                    cv2.putText(frame, "GRAB",
                                (pinch_pt[0] + 24, pinch_pt[1] + 6),
                                cv2.FONT_HERSHEY_SIMPLEX, 0.55,
                                (0, 200, 255), 1, cv2.LINE_AA)

                # ══════════════════════════
                #  IDLE — commit any stroke
                # ══════════════════════════
                else:
                    if current_stroke and len(current_stroke) > 1:
                        strokes.append(current_stroke[:])
                        current_stroke = []
                    prev_point    = None
                    selected_idx  = None
                    last_pinch_pt = None

                # Subtle hand skeleton (dim red tones to match aesthetic)
                mp_drawing.draw_landmarks(
                    frame, hand_lm, mp_hands.HAND_CONNECTIONS,
                    mp_drawing.DrawingSpec(color=(20, 10, 60), thickness=1, circle_radius=2),
                    mp_drawing.DrawingSpec(color=(30, 15, 80), thickness=1),
                )

            else:
                # No hand detected — commit in-progress stroke
                if current_stroke and len(current_stroke) > 1:
                    strokes.append(current_stroke[:])
                    current_stroke = []
                prev_point    = None
                selected_idx  = None
                smooth_buf.clear()

            # ── Age particles & remove dead ones ─────────────
            particles = [p for p in particles if p.update()]

            # ── Render all neon strokes onto canvas ──────────
            canvas[:] = 0   # clear last frame's glow (re-drawn every frame)

            all_strokes = strokes + ([current_stroke] if len(current_stroke) > 1 else [])
            for stroke in all_strokes:
                if len(stroke) >= 2:
                    draw_neon_stroke(canvas, stroke)

            # Selected stroke gets an extra bright re-draw pass
            if selected_idx is not None and selected_idx < len(strokes):
                draw_neon_stroke(canvas, strokes[selected_idx])

            # ── Render particles onto canvas ──────────────────
            render_particles(canvas, particles)

            # ── Additive blend: neon + particles → camera ────
            # cv2.add() clamps at 255, so neon "adds light" like a real glow
            cv2.add(frame, canvas, frame)

            # ── Palm-flash countdown ─────────────────────────
            if palm_flash > 0:
                palm_flash -= 1

            # ── HUD ──────────────────────────────────────────
            draw_hud(frame, mode, fps, selected_idx is not None, palm_flash)

            # ── Display ──────────────────────────────────────
            cv2.imshow("🔴 RED LASER AIR WRITING — Cyberpunk v2", frame)

            key = cv2.waitKey(1) & 0xFF
            if key in (ord("q"), ord("Q"), 27):
                break

    cap.release()
    cv2.destroyAllWindows()
    print("\n✅  Session ended. Goodbye!\n")


if __name__ == "__main__":
    main()