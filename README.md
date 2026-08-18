# ✦ NEON AIR WRITING SYSTEM ✦
### Cyberpunk Hologram Drawing — Iron Man Style

Draw glowing neon laser lines in the air using only your index finger and a webcam.

---

## 🚀 Quick Start

### 1. Requirements
- Python 3.9 or higher
- A webcam (built-in or USB)
- Good lighting (helps hand detection)

### 2. Install Dependencies
```bash
pip install -r requirements.txt
```

### 3. Run
```bash
python main.py
```

---

## 🎮 Controls

| Gesture | Action |
|--------|--------|
| ☝️ **One finger up** | Draw mode — trace a glowing neon line |
| ✌️ **Two fingers up** | Erase mode — clears the entire canvas |
| 🤌 **Pinch (thumb + index close)** | Select & move your drawing |
| **Q / ESC** | Quit |

---

## ✨ Features

- **Continuous smooth neon stroke** — never broken, always flowing
- **Gaussian blur glow layers** — cinematic laser/hologram effect
- **Smooth motion filtering** — averages last 6 positions to kill hand shake
- **Additive blending** — neon adds light on top of the camera feed (like real glowing)
- **Stroke management** — multiple strokes stored separately, all rendered together
- **Select & Move** — pinch near any drawing to grab and reposition it
- **60 FPS optimized** rendering
- **Dark cyberpunk HUD** — mode indicator, FPS counter, corner decorations

---

## 🔧 Customization

Open `main.py` and edit the CONFIG block at the top:

```python
SMOOTHING_WINDOW  = 6      # Higher = smoother but more lag
MIN_DRAW_DISTANCE = 4      # Lower = more detail, more noise
GLOW_LAYERS       = 4      # More = richer glow, slightly slower
NEON_COLOR        = (255, 220, 0)   # BGR core color
GLOW_COLOR        = (255, 180, 0)   # BGR glow color
LINE_THICKNESS    = 3               # Core line width
PINCH_THRESHOLD   = 0.07            # Pinch sensitivity
```

**Want different neon colors?**
```python
# Hot pink neon
NEON_COLOR = (180, 0, 255)
GLOW_COLOR = (120, 0, 200)

# Green Matrix style
NEON_COLOR = (0, 255, 80)
GLOW_COLOR = (0, 180, 40)

# Orange fire
NEON_COLOR = (0, 140, 255)
GLOW_COLOR = (0, 80, 200)
```

---

## 🐛 Troubleshooting

| Problem | Fix |
|---------|-----|
| Camera won't open | Change `cv2.VideoCapture(0)` to `VideoCapture(1)` or `2` |
| Hand not detected | Improve lighting, keep hand within frame, avoid busy backgrounds |
| Drawing feels shaky | Increase `SMOOTHING_WINDOW` to 8–10 |
| Low FPS | Reduce `GLOW_LAYERS` to 2, or lower camera resolution |
| mediapipe install fails | Try `pip install mediapipe==0.10.9` |

---

## 📁 File Structure
```
air_writing/
├── main.py           ← Full application (single file)
├── requirements.txt  ← Python dependencies
└── README.md         ← This file
```

---

## 🧠 How It Works

1. **MediaPipe Hands** detects 21 hand landmarks in real-time
2. The **index fingertip** (landmark #8) is tracked
3. A **rolling average buffer** smooths the last 6 positions
4. In **DRAW mode**, points are accumulated into a stroke list
5. Each frame, all strokes are re-rendered using **layered Gaussian blur** to create the glow
6. The glow canvas is **additively blended** onto the webcam feed
7. In **PINCH mode**, the closest stroke is translated by the delta of the pinch midpoint

---

*Built with OpenCV · MediaPipe · NumPy · Python*
