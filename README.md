# ⚡ AI Workout Trainer

> **Real-time AI-powered fitness coaching in your browser — no app required.**

Built with **Flask**, **MediaPipe**, **OpenCV**, and **ReportLab**. Point your camera at yourself, pick an exercise, and the AI counts your reps, scores your form, and tells you what to fix — live.

---

## 🚀 Live Demo

Deploy on [Render.com](https://render.com) — see [Deployment](#-deployment-on-render) below.

---

## ✨ Features

| Feature | Details |
|---|---|
| 🎯 Live AI Trainer | Real-time pose detection, rep counting, form feedback |
| 🏋️ 10 Exercises | Squat, Push-up, Bicep Curl, Lunge, Shoulder Press, Plank, Jumping Jacks, High Knees, Arm Raises, Side Lunge |
| 🎯 26 Fitness Goals | Weight Loss, Muscle Gain, HIIT, Endurance, Senior Fitness and more |
| 📋 Daily Plan | Personalised workout plan with sets, reps, rest periods |
| 📊 Dashboard | Session stats, accuracy scores, mistake breakdown |
| 👤 Profile | Name, age, height, weight, gender, fitness goal |
| 🥩 Nutrition | Protein calculator + goal-based daily meal plan |
| 📄 Nutrition PDF | Download a personalised Nutrition Plan PDF in one click |

---

## 🛠 Tech Stack

- **Backend** — Python 3, Flask, Flask-CORS
- **Pose Detection** — MediaPipe 0.10.32
- **Computer Vision** — OpenCV (headless)
- **PDF Generation** — ReportLab
- **Numerics** — NumPy
- **Production Server** — Gunicorn
- **Frontend** — Vanilla JS, HTML5, CSS3

---

## 📁 Project Structure

```
ai_workout_trainer_v4/
├── app.py                  # Flask app — routes, exercise detectors, PDF generator
├── templates/
│   ├── index.html          # Main page — Live Trainer, Daily Plan, Dashboard tabs
│   └── profile.html        # Profile form, nutrition display, PDF download button
├── static/
│   ├── style.css           # Full UI stylesheet (dark mode, responsive)
│   └── script.js           # Camera feed, frame capture, API calls
├── requirements.txt        # Python dependencies
└── Procfile                # Render/Heroku start command
```

---

## ⚙️ Local Setup

### Prerequisites
- Python 3.10+
- A webcam

### Steps

```bash
# 1. Clone the repository
git clone https://github.com/your-username/ai-workout-trainer.git
cd ai-workout-trainer

# 2. Create and activate a virtual environment
python -m venv venv
source venv/bin/activate        # Mac / Linux
venv\Scripts\activate           # Windows

# 3. Install dependencies
pip install -r requirements.txt

# 4. Run the app
python app.py
```

Then open **http://localhost:5000** in your browser.

---

## 📄 Nutrition Plan PDF

On the **Profile** page:
1. Fill in your profile and click **Save & Generate Plan**
2. Scroll down and click **⬇ Download Nutrition Plan PDF**
3. `nutrition_plan.pdf` downloads automatically

The PDF includes:
- User information (name, age, height, weight, goal)
- Daily protein requirement (Weight × 1.6–2.2 g/day)
- 5-meal daily diet plan tailored to your goal
- Workout plan table (exercises, sets, reps, rest)
- Recommended high-protein foods

**Endpoints:**
```
POST /download-nutrition-pdf        ← primary
POST /api/download_nutrition_pdf    ← legacy
```

---

## 🌐 Deployment on Render

1. Push this repository to GitHub
2. Go to [render.com](https://render.com) → **New** → **Web Service** → connect your repo
3. Set the following:

| Setting | Value |
|---|---|
| Build Command | `pip install -r requirements.txt` |
| Start Command | `gunicorn app:app` |
| Environment | Python 3 |

4. Click **Deploy** — Render handles the rest.

> The `Procfile` already contains `web: gunicorn app:app` so the start command is auto-detected.

---

## 🔗 API Endpoints

| Method | Route | Description |
|---|---|---|
| GET | `/` | Main application page |
| GET | `/profile` | Profile & nutrition page |
| GET | `/api/goals` | All 26 fitness goals |
| POST | `/api/process_frame` | Process camera frame → annotated frame + rep data |
| POST | `/api/save_profile` | Save profile → return diet, plan, recommendations |
| GET | `/api/get_profile` | Load saved profile |
| POST | `/api/get_daily_plan` | Generate plan from profile JSON |
| GET | `/api/dashboard_stats` | Session workout statistics |
| GET | `/api/workout_history` | Per-exercise rep history |
| POST | `/api/reset_exercise` | Reset rep counter for an exercise |
| POST | `/api/get_summary` | Summary stats for a completed set |
| POST | `/download-nutrition-pdf` | Download Nutrition Plan PDF |

---

## 📦 Dependencies

```txt
flask
flask-cors
mediapipe==0.10.32
opencv-python-headless
numpy
reportlab
gunicorn
```

Install with:
```bash
pip install -r requirements.txt
```

---

## 📝 Notes

- Session data (rep counts, history) is stored **in memory** — it resets on server restart. No database is used.
- Camera access requires **HTTPS** in production. Render provides SSL automatically.
- `mediapipe==0.10.32` is pinned — the Pose API changed in later versions.
- `opencv-python-headless` is used to avoid GUI dependencies on servers.
- The PDF is generated **on demand** — no files are stored on disk.

---

## 🤝 Contributing

1. Fork the repo
2. Create a feature branch: `git checkout -b feature/your-feature`
3. Commit your changes: `git commit -m "Add your feature"`
4. Push to the branch: `git push origin feature/your-feature`
5. Open a Pull Request

---

## 📄 License

This project is open source. Feel free to use, modify, and distribute.

---

> ⚡ **AI Workout Trainer** — Built with Flask, MediaPipe & ReportLab
