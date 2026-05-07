import os, base64, math, time
from flask import Flask, render_template, request, jsonify, session, send_file
from flask_cors import CORS
from io import BytesIO

try:
    import numpy as np
    import cv2
    import mediapipe as mp
    CV_OK = True
except Exception:
    CV_OK = False

try:
    from reportlab.lib.pagesizes import A4
    from reportlab.lib import colors
    from reportlab.lib.units import cm
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.lib.enums import TA_CENTER
    from reportlab.platypus import (SimpleDocTemplate, Paragraph, Spacer,
                                     Table, TableStyle, HRFlowable)
    REPORTLAB_OK = True
except ImportError:
    REPORTLAB_OK = False

app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY', 'fn_v4_x9k2m8p3q7r1s6t4_2026')
app.config['SESSION_COOKIE_SAMESITE'] = 'Lax'
app.config['SESSION_COOKIE_SECURE'] = os.environ.get('VERCEL', False) and True
CORS(app)

# ── MediaPipe ────────────────────────────────────────────────────────────────
mp_pose    = mp.solutions.pose
mp_drawing = mp.solutions.drawing_utils

pose_detector = mp_pose.Pose(
    static_image_mode=False, model_complexity=1,
    smooth_landmarks=True,   enable_segmentation=False,
    min_detection_confidence=0.5, min_tracking_confidence=0.5,
)

# ── Helpers ───────────────────────────────────────────────────────────────────
def angle3(a, b, c):
    a, b, c = np.array(a), np.array(b), np.array(c)
    ba, bc  = a - b, c - b
    cosv    = np.dot(ba, bc) / (np.linalg.norm(ba) * np.linalg.norm(bc) + 1e-6)
    return math.degrees(math.acos(np.clip(cosv, -1.0, 1.0)))

def lm(landmarks, idx):
    p = landmarks[idx]
    return [p.x, p.y]

# ── Global state ──────────────────────────────────────────────────────────────
ex_state   = {}   # keyed by "{session_id}_{exercise}"
dash_state = {}   # keyed by session_id

def get_ex(sid, ex):
    key = f"{sid}_{ex}"
    if key not in ex_state:
        ex_state[key] = dict(
            stage=None, reps=0, correct_reps=0, wrong_reps=0,
            mistakes=[], last_angle=0, plank_start=None,
            jj_stage=None, hk_stage=None,
            form_acc_sum=0, form_checks=0,
        )
    return ex_state[key]

def get_dash(sid):
    if sid not in dash_state:
        dash_state[sid] = dict(acc_sum=0, acc_cnt=0)
    return dash_state[sid]

# ═══════════════════════════════════════════════════════════════════════════
# EXERCISE DETECTORS
# ═══════════════════════════════════════════════════════════════════════════

def det_squat(L, st):
    ang = angle3(lm(L,23), lm(L,25), lm(L,27))
    st['last_angle'] = round(ang, 1)
    fb, ok = "Stand feet shoulder-width apart.", True
    if ang < 90:
        if st['stage'] == 'up': st['stage'] = 'down'
        fb = "Great depth! Drive back up."
    elif ang > 160:
        if st['stage'] == 'down':
            st['reps'] += 1; st['correct_reps'] += 1; st['stage'] = 'up'
            fb = f"Rep {st['reps']} complete! Perfect squat."
        else:
            st['stage'] = 'up'; fb = "Lower hips – squat deeper!"
    else:
        fb = "Keep going – lower your hips more."
    if ang < 120:
        sh = lm(L,11); hip = lm(L,23)
        if abs(sh[0]-hip[0]) > 0.14:
            fb="Back leaning forward – keep chest up!"; ok=False
            if "Back leaning forward" not in st['mistakes']: st['mistakes'].append("Back leaning forward")
        lk=lm(L,25); rk=lm(L,26); rh=lm(L,24)
        if (lk[0]-hip[0])>0.07 or (rh[0]-rk[0])>0.07:
            fb="Knees moving inward – push knees outward!"; ok=False
            if "Knees caving inward" not in st['mistakes']: st['mistakes'].append("Knees caving inward")
    acc = max(0, min(100, int((1-(ang-90)/70)*100))) if ang<160 else 0
    return fb, ok, acc

def det_pushup(L, st):
    ang = angle3(lm(L,11), lm(L,13), lm(L,15))
    st['last_angle'] = round(ang, 1)
    fb, ok = "Plank position – hands under shoulders.", True
    if ang < 90:
        if st['stage']=='up': st['stage']='down'
        fb="Good depth! Push back up."
    elif ang > 160:
        if st['stage']=='down':
            st['reps']+=1; st['correct_reps']+=1; st['stage']='up'
            fb=f"Rep {st['reps']} complete! Lower again."
        else:
            st['stage']='up'; fb="Lower chest toward the floor."
    elif 90<ang<140 and st['stage']=='up':
        fb="Half push-up detected – go lower!"; ok=False
        if "Half push-up" not in st['mistakes']: st['mistakes'].append("Half push-up")
    sw=abs(lm(L,12)[0]-lm(L,11)[0]); ew=abs(lm(L,14)[0]-lm(L,13)[0])
    if ew>sw*1.45:
        fb="Elbows too wide – keep elbows closer to body!"; ok=False
        if "Elbows too wide" not in st['mistakes']: st['mistakes'].append("Elbows too wide")
    body=angle3(lm(L,11), lm(L,23), lm(L,27))
    if body<155:
        fb="Hips sagging – keep body in straight line!"; ok=False
        if "Hips sagging" not in st['mistakes']: st['mistakes'].append("Hips sagging")
    acc = max(0, min(100, int((1-ang/90)*100))) if ang<90 else 0
    return fb, ok, acc

def det_bicep_curl(L, st):
    ang = angle3(lm(L,11), lm(L,13), lm(L,15))
    st['last_angle'] = round(ang, 1)
    fb, ok = "Extend arm fully, palm up.", True
    if ang<50:
        if st['stage']=='down': st['stage']='up'
        fb="Good curl! Lower slowly."
    elif ang>160:
        if st['stage']=='up':
            st['reps']+=1; st['correct_reps']+=1; st['stage']='down'
            fb=f"Rep {st['reps']} complete! Full range."
        else:
            st['stage']='down'; fb="Curl arm all the way up."
    else:
        fb="Keep curling – bring wrist to shoulder."
    if abs(lm(L,13)[0]-lm(L,11)[0])>0.10:
        fb="Elbow drifting – keep elbow pinned to side!"; ok=False
        if "Elbow drifting" not in st['mistakes']: st['mistakes'].append("Elbow drifting")
    acc = max(0, min(100, int((160-ang)/110*100))) if ang<160 else 0
    return fb, ok, acc

def det_lunge(L, st):
    ang = angle3(lm(L,23), lm(L,25), lm(L,27))
    st['last_angle'] = round(ang, 1)
    fb, ok = "Step forward – feet hip-width apart.", True
    if ang<95:
        if st['stage']=='up': st['stage']='down'
        fb="Great lunge depth! Drive back up."
    elif ang>165:
        if st['stage']=='down':
            st['reps']+=1; st['correct_reps']+=1; st['stage']='up'
            fb=f"Rep {st['reps']} complete! Switch legs."
        else:
            st['stage']='up'; fb="Step forward and lower knee."
    if abs(lm(L,11)[0]-lm(L,23)[0])>0.12:
        fb="Keep chest up – torso upright!"; ok=False
        if "Torso leaning" not in st['mistakes']: st['mistakes'].append("Torso leaning")
    acc = max(0, min(100, int((165-ang)/70*100))) if ang<165 else 0
    return fb, ok, acc

def det_shoulder_press(L, st):
    ang = angle3(lm(L,11), lm(L,13), lm(L,15))
    st['last_angle'] = round(ang, 1)
    fb, ok = "Weights at shoulders, core braced.", True
    if ang>160:
        if st['stage']=='down': st['stage']='up'
        fb="Full lockout! Lower with control."
    elif ang<80:
        if st['stage']=='up':
            st['reps']+=1; st['correct_reps']+=1; st['stage']='down'
            fb=f"Rep {st['reps']} complete! Press again."
        else:
            st['stage']='down'; fb="Press weights overhead."
    if abs(lm(L,11)[0]-lm(L,23)[0])>0.10:
        fb="Don't arch back – brace core!"; ok=False
        if "Lower back arch" not in st['mistakes']: st['mistakes'].append("Lower back arch")
    acc = max(0, min(100, int((ang-80)/80*100))) if ang>80 else 100
    return fb, ok, acc

def det_plank(L, st):
    ang = angle3(lm(L,11), lm(L,23), lm(L,27))
    st['last_angle'] = round(ang, 1)
    ok = True
    if 155<ang<205:
        if st['plank_start'] is None: st['plank_start']=time.time()
        dur=int(time.time()-st['plank_start']); st['reps']=dur; st['correct_reps']=dur//10
        fb=f"Solid plank! {dur}s elapsed."
    elif ang<=155:
        st['plank_start']=None; fb="Hips too high – lower them!"; ok=False
        if "Hips too high" not in st['mistakes']: st['mistakes'].append("Hips too high")
    else:
        st['plank_start']=None; fb="Hips sagging – raise them!"; ok=False
        if "Hips sagging" not in st['mistakes']: st['mistakes'].append("Hips sagging")
    acc = max(0, min(100, int((1-abs(180-ang)/25)*100))) if 155<ang<205 else 0
    return fb, ok, acc

def det_jumping_jacks(L, st):
    arm_sp=abs(lm(L,16)[0]-lm(L,15)[0]); leg_sp=abs(lm(L,28)[0]-lm(L,27)[0])
    st['last_angle']=round(arm_sp*100,1); ok=True
    if arm_sp>0.50 and leg_sp>0.20:
        if st['jj_stage']=='closed':
            st['reps']+=1; st['correct_reps']+=1; fb=f"Rep {st['reps']}! Keep rhythm."
        else: fb="Arms and legs wide! Good."
        st['jj_stage']='open'
    elif arm_sp<0.25:
        if st['jj_stage']=='open':
            st['reps']+=1; st['correct_reps']+=1; fb=f"Rep {st['reps']}! Jump wide again."
        else: fb="Jump – spread arms and legs!"
        st['jj_stage']='closed'
    else: fb="Spread arms and legs wider!"
    acc=max(0,min(100,int(arm_sp/0.50*100)))
    return fb, ok, acc

def det_high_knees(L, st):
    lr=lm(L,23)[1]-lm(L,25)[1]; rr=lm(L,24)[1]-lm(L,26)[1]
    st['last_angle']=round(max(lr,rr)*100,1); ok=True
    if lr>0.06 or rr>0.06:
        if st['hk_stage']=='down':
            st['reps']+=1; st['correct_reps']+=1; fb=f"Rep {st['reps']}! Drive knees high!"
        else: fb="Knee up! Great high knees!"
        st['hk_stage']='up'
    else:
        if st['hk_stage']=='up': st['hk_stage']='down'
        fb="Raise knees higher – above hip level!"
        if st['reps']>0:
            ok=False
            if "Knees not high enough" not in st['mistakes']: st['mistakes'].append("Knees not high enough")
    acc=max(0,min(100,int(max(lr,rr)/0.06*100)))
    return fb, ok, acc

def det_arm_raises(L, st):
    h=lm(L,11)[1]-lm(L,15)[1]; st['last_angle']=round(h*100,1); ok=True
    if h>0.12:
        if st['stage']=='down': st['stage']='up'
        fb="Arms raised! Lower with control."
    elif h<-0.05:
        if st['stage']=='up':
            st['reps']+=1; st['correct_reps']+=1; st['stage']='down'
            fb=f"Rep {st['reps']} complete! Raise again."
        else:
            st['stage']='down'; fb="Raise arms to shoulder height."
    else: fb="Lift arms parallel to floor."
    acc=max(0,min(100,int(h/0.12*100)))
    return fb, ok, acc

def det_side_lunge(L, st):
    ang=angle3(lm(L,23), lm(L,25), lm(L,27)); st['last_angle']=round(ang,1); ok=True
    if ang<100:
        if st['stage']=='up': st['stage']='down'
        fb="Deep side lunge! Push back up."
    elif ang>165:
        if st['stage']=='down':
            st['reps']+=1; st['correct_reps']+=1; st['stage']='up'
            fb=f"Rep {st['reps']} complete! Step wide again."
        else:
            st['stage']='up'; fb="Step wide and bend knee."
    else: fb="Sink lower – knee to 90 degrees."
    if abs(lm(L,25)[0]-lm(L,27)[0])>0.10:
        fb="Knee over toes – align knee over foot!"; ok=False
        if "Knee over toes" not in st['mistakes']: st['mistakes'].append("Knee over toes")
    acc=max(0,min(100,int((165-ang)/65*100))) if ang<165 else 0
    return fb, ok, acc

DETECTORS = {
    'squat':det_squat,'pushup':det_pushup,'bicep_curl':det_bicep_curl,
    'lunge':det_lunge,'shoulder_press':det_shoulder_press,'plank':det_plank,
    'jumping_jacks':det_jumping_jacks,'high_knees':det_high_knees,
    'arm_raises':det_arm_raises,'side_lunge':det_side_lunge,
}

# ── Skeleton drawing ──────────────────────────────────────────────────────────
CONNS=[
    (11,12),(11,23),(12,24),(23,24),
    (11,13),(13,15),(12,14),(14,16),
    (23,25),(25,27),(27,29),(29,31),
    (24,26),(26,28),(28,30),(30,32),
]
KEY_JOINTS=[11,12,13,14,15,16,23,24,25,26,27,28]

def draw_skeleton(frame, pose_lm, ok=True):
    h,w=frame.shape[:2]
    cc=(50,220,120) if ok else (60,100,255)
    pc=(0,200,255) if ok else (50,50,255)
    L=pose_lm.landmark
    for a,b in CONNS:
        la,lb=L[a],L[b]
        if la.visibility<0.35 or lb.visibility<0.35: continue
        cv2.line(frame,(int(la.x*w),int(la.y*h)),(int(lb.x*w),int(lb.y*h)),cc,3,cv2.LINE_AA)
    for i in KEY_JOINTS:
        lk=L[i]
        if lk.visibility<0.35: continue
        x,y=int(lk.x*w),int(lk.y*h)
        cv2.circle(frame,(x,y),7,pc,-1,cv2.LINE_AA)
        cv2.circle(frame,(x,y),9,(255,255,255),2,cv2.LINE_AA)
    return frame

def add_hud(frame, ex, reps, angle, ok, acc, fb):
    h,w=frame.shape[:2]
    ov=frame.copy()
    cv2.rectangle(ov,(0,0),(w,52),(8,10,18),-1)
    cv2.addWeighted(ov,0.68,frame,0.32,0,frame)
    cv2.putText(frame,ex.replace('_',' ').upper(),(12,36),cv2.FONT_HERSHEY_DUPLEX,0.90,(0,200,255),2,cv2.LINE_AA)
    cv2.putText(frame,f"REPS:{reps}",(w//2-65,36),cv2.FONT_HERSHEY_DUPLEX,0.95,(255,255,255),2,cv2.LINE_AA)
    ac=(50,220,120) if acc>70 else (50,180,255) if acc>40 else (60,60,255)
    cv2.putText(frame,f"ACC:{acc}%",(w-148,36),cv2.FONT_HERSHEY_DUPLEX,0.80,ac,2,cv2.LINE_AA)
    ov2=frame.copy(); by=h-58
    cv2.rectangle(ov2,(0,by),(w,h),(8,10,18),-1)
    cv2.addWeighted(ov2,0.72,frame,0.28,0,frame)
    fc=(50,220,120) if ok else (60,100,255)
    cv2.putText(frame,"FORM OK" if ok else "FIX FORM",(12,by+22),cv2.FONT_HERSHEY_DUPLEX,0.60,fc,2,cv2.LINE_AA)
    cv2.putText(frame,f"Ang:{angle}",(12,by+44),cv2.FONT_HERSHEY_SIMPLEX,0.48,(160,160,160),1,cv2.LINE_AA)
    cv2.putText(frame,fb[:62]+('…' if len(fb)>62 else ''),(130,by+34),cv2.FONT_HERSHEY_SIMPLEX,0.52,(225,225,225),1,cv2.LINE_AA)
    return frame

# ═══════════════════════════════════════════════════════════════════════════
# EXPANDED GOALS — 26 total
# ═══════════════════════════════════════════════════════════════════════════

ALL_GOALS = [
    # Original 4
    ("weight_loss",           "Weight Loss"),
    ("muscle_gain",           "Muscle Gain"),
    ("body_recomposition",    "Body Recomposition"),
    ("general_fitness",       "General Fitness"),
    # Added batch 1
    ("strength_training",     "Strength Training"),
    ("endurance_training",    "Endurance Training"),
    ("fat_loss",              "Fat Loss"),
    ("athletic_performance",  "Athletic Performance"),
    ("flexibility_mobility",  "Flexibility & Mobility"),
    ("posture_improvement",   "Posture Improvement"),
    ("rehabilitation",        "Rehabilitation / Injury Recovery"),
    # Added batch 2
    ("core_strength",         "Core Strength"),
    ("lean_muscle",           "Lean Muscle Building"),
    ("cardio_fitness",        "Cardio Fitness"),
    ("functional_fitness",    "Functional Fitness"),
    ("calisthenics",          "Calisthenics Training"),
    ("body_toning",           "Body Toning"),
    ("stamina",               "Stamina Improvement"),
    ("hiit",                  "HIIT Conditioning"),
    ("speed_agility",         "Speed & Agility"),
    ("balance_stability",     "Balance & Stability"),
    ("sports_performance",    "Sports Performance"),
    ("beginner_fitness",      "Beginner Fitness"),
    ("advanced_training",     "Advanced Training"),
    ("senior_fitness",        "Senior Fitness"),
    ("home_workout",          "Home Workout Training"),
]

GOAL_LABELS = {k: v for k, v in ALL_GOALS}

# ── Meal templates keyed by goal ──────────────────────────────────────────────
MEALS = {
    "weight_loss": dict(
        breakfast="Oats (50g) + Milk (200ml) + 2 Egg whites",
        lunch="Brown Rice (100g) + Grilled Chicken (150g) + Salad",
        snack="Greek Yogurt (150g) + Apple",
        dinner="Chapati (2) + Dal (1 cup) + Paneer (100g)",
        pre_bed="Low-fat Milk (200ml)",
        foods=["Chicken Breast","Fish","Egg whites","Oats","Greek Yogurt","Vegetables","Lentils"],
    ),
    "muscle_gain": dict(
        breakfast="Oats (80g) + Whole Milk (300ml) + 3 Eggs",
        lunch="Rice (200g) + Chicken Breast (200g) + Vegetables",
        snack="Peanut Butter Sandwich + Banana",
        dinner="Chapati (3) + Dal (1.5 cups) + 2 Eggs",
        pre_bed="Full-fat Milk (300ml) + Peanut Butter (30g)",
        foods=["Chicken Breast","Eggs","Paneer","Fish","Milk","Peanut Butter","Tofu","Lentils"],
    ),
    "body_recomposition": dict(
        breakfast="Oats (60g) + Milk (250ml) + 2 Eggs",
        lunch="Rice (150g) + Chicken or Paneer (150g) + Vegetables",
        snack="Greek Yogurt (150g) + Mixed Nuts (30g)",
        dinner="Chapati (2) + Dal (1 cup) + Fish (150g)",
        pre_bed="Milk (250ml)",
        foods=["Chicken Breast","Fish","Eggs","Paneer","Greek Yogurt","Tofu","Peanut Butter","Lentils"],
    ),
    "strength_training": dict(
        breakfast="Oats (80g) + Milk (300ml) + 3 Eggs",
        lunch="Rice (200g) + Chicken (200g) + Vegetables",
        snack="Peanut Butter (30g) + Banana + Milk",
        dinner="Chapati (3) + Dal (1.5 cups) + Eggs (2)",
        pre_bed="Full-fat Milk (300ml)",
        foods=["Chicken Breast","Eggs","Paneer","Fish","Milk","Peanut Butter","Lentils","Tofu"],
    ),
    "endurance_training": dict(
        breakfast="Oats (70g) + Banana + Milk (250ml)",
        lunch="Rice (180g) + Chicken (150g) + Salad",
        snack="Energy bar or Dates (5) + Nuts",
        dinner="Chapati (3) + Dal (1 cup) + Curd",
        pre_bed="Milk (250ml) + Honey",
        foods=["Oats","Banana","Dates","Rice","Chicken Breast","Eggs","Lentils","Greek Yogurt"],
    ),
    "fat_loss": dict(
        breakfast="Oats (40g) + Egg whites (3) + Green tea",
        lunch="Brown Rice (80g) + Grilled Chicken (150g) + Salad",
        snack="Cucumber + Greek Yogurt (100g)",
        dinner="Chapati (1) + Dal (1 cup) + Grilled Fish (120g)",
        pre_bed="Low-fat Milk (150ml)",
        foods=["Chicken Breast","Fish","Egg whites","Oats","Greek Yogurt","Vegetables","Lentils"],
    ),
    "athletic_performance": dict(
        breakfast="Oats (80g) + Milk (300ml) + 3 Eggs + Banana",
        lunch="Rice (200g) + Chicken (200g) + Vegetables + Curd",
        snack="Peanut Butter Sandwich + Sports drink",
        dinner="Chapati (3) + Dal (1.5 cups) + Eggs (2) + Salad",
        pre_bed="Milk (300ml) + Peanut Butter",
        foods=["Chicken Breast","Eggs","Paneer","Fish","Milk","Peanut Butter","Banana","Lentils"],
    ),
    "flexibility_mobility": dict(
        breakfast="Oats (50g) + Milk (200ml) + 2 Eggs",
        lunch="Rice (150g) + Fish (150g) + Vegetables",
        snack="Greek Yogurt (150g) + Berries",
        dinner="Chapati (2) + Dal (1 cup) + Paneer (100g)",
        pre_bed="Turmeric Milk (250ml)",
        foods=["Fish","Eggs","Paneer","Greek Yogurt","Milk","Tofu","Lentils","Vegetables"],
    ),
    "core_strength": dict(
        breakfast="Oats (60g) + Eggs (2) + Milk (200ml)",
        lunch="Rice (150g) + Chicken (150g) + Vegetables",
        snack="Peanut Butter (20g) + Rice cake",
        dinner="Chapati (2) + Dal (1 cup) + Eggs (1)",
        pre_bed="Milk (200ml)",
        foods=["Eggs","Chicken Breast","Paneer","Fish","Milk","Peanut Butter","Lentils"],
    ),
    "lean_muscle": dict(
        breakfast="Oats (60g) + Egg whites (3) + Milk (200ml)",
        lunch="Brown Rice (150g) + Chicken (180g) + Salad",
        snack="Greek Yogurt (150g) + Almonds",
        dinner="Chapati (2) + Dal (1 cup) + Fish (150g)",
        pre_bed="Milk (200ml)",
        foods=["Chicken Breast","Fish","Egg whites","Greek Yogurt","Tofu","Paneer","Lentils"],
    ),
    "cardio_fitness": dict(
        breakfast="Oats (50g) + Banana + Milk (200ml)",
        lunch="Rice (150g) + Chicken (150g) + Salad",
        snack="Dates (5) + Nuts (20g)",
        dinner="Chapati (2) + Dal (1 cup) + Curd",
        pre_bed="Milk (200ml)",
        foods=["Oats","Banana","Chicken Breast","Eggs","Lentils","Greek Yogurt","Milk"],
    ),
    "hiit": dict(
        breakfast="Oats (60g) + Eggs (2) + Milk (250ml)",
        lunch="Brown Rice (150g) + Chicken (150g) + Vegetables",
        snack="Peanut Butter (25g) + Banana",
        dinner="Chapati (2) + Dal (1 cup) + Paneer (100g)",
        pre_bed="Milk (200ml)",
        foods=["Chicken Breast","Eggs","Peanut Butter","Banana","Oats","Lentils","Greek Yogurt"],
    ),
    "senior_fitness": dict(
        breakfast="Oats (50g) + Milk (250ml) + 1 Egg",
        lunch="Rice (120g) + Fish (120g) + Vegetables",
        snack="Greek Yogurt (150g) + Banana",
        dinner="Chapati (2) + Dal (1 cup) + Paneer (80g)",
        pre_bed="Warm Milk (250ml)",
        foods=["Fish","Eggs","Milk","Greek Yogurt","Paneer","Tofu","Lentils","Vegetables"],
    ),
}

def get_meals(goal):
    """Return meals for goal, falling back to general_fitness template."""
    direct_map = {
        "posture_improvement": "general_fitness",
        "rehabilitation":      "general_fitness",
        "functional_fitness":  "general_fitness",
        "calisthenics":        "muscle_gain",
        "body_toning":         "weight_loss",
        "stamina":             "endurance_training",
        "speed_agility":       "athletic_performance",
        "balance_stability":   "general_fitness",
        "sports_performance":  "athletic_performance",
        "beginner_fitness":    "general_fitness",
        "advanced_training":   "muscle_gain",
        "home_workout":        "general_fitness",
    }
    key = direct_map.get(goal, goal)
    return MEALS.get(key, MEALS["general_fitness"])

GENERAL_MEALS = dict(
    breakfast="Oats (50g) + Milk (200ml) + 2 Eggs",
    lunch="Rice (150g) + Chicken or Paneer (120g) + Vegetables",
    snack="Peanut Butter Sandwich",
    dinner="Chapati (2) + Dal (1 cup) + 1 Egg",
    pre_bed="Milk (200ml)",
    foods=["Eggs","Chicken Breast","Fish","Paneer","Milk","Greek Yogurt","Tofu","Peanut Butter","Lentils"],
)
MEALS["general_fitness"] = GENERAL_MEALS

# ── Workout plans keyed by goal ───────────────────────────────────────────────
PLANS = {
    "muscle_gain": dict(label="Muscle Gain Plan",
        warmup=[{"name":"Jumping Jacks","sets":2,"reps":"15","rest":"30s"}],
        workout=[
            {"name":"Squat","sets":4,"reps":"12","rest":"60s","key":"squat"},
            {"name":"Push-up","sets":4,"reps":"10","rest":"60s","key":"pushup"},
            {"name":"Shoulder Press","sets":3,"reps":"10","rest":"60s","key":"shoulder_press"},
            {"name":"Bicep Curl","sets":3,"reps":"12","rest":"45s","key":"bicep_curl"},
            {"name":"Lunge","sets":3,"reps":"10","rest":"60s","key":"lunge"},
        ],
        cooldown=[{"name":"Full Body Stretch","duration":"5 min"}],
    ),
    "weight_loss": dict(label="Fat Burn Plan",
        warmup=[{"name":"High Knees","sets":1,"reps":"30s","rest":"15s"}],
        workout=[
            {"name":"Jumping Jacks","sets":3,"reps":"20","rest":"30s","key":"jumping_jacks"},
            {"name":"High Knees","sets":3,"reps":"30s","rest":"30s","key":"high_knees"},
            {"name":"Lunge","sets":3,"reps":"12","rest":"45s","key":"lunge"},
            {"name":"Squat","sets":3,"reps":"15","rest":"45s","key":"squat"},
            {"name":"Plank","sets":3,"reps":"30s","rest":"30s","key":"plank"},
        ],
        cooldown=[{"name":"Stretching & Breathing","duration":"5 min"}],
    ),
    "body_recomposition": dict(label="Recomposition Plan",
        warmup=[{"name":"Jumping Jacks","sets":2,"reps":"15","rest":"20s"}],
        workout=[
            {"name":"Squat","sets":3,"reps":"12","rest":"45s","key":"squat"},
            {"name":"Push-up","sets":3,"reps":"10","rest":"45s","key":"pushup"},
            {"name":"Bicep Curl","sets":3,"reps":"12","rest":"45s","key":"bicep_curl"},
            {"name":"Jumping Jacks","sets":3,"reps":"20","rest":"30s","key":"jumping_jacks"},
            {"name":"Plank","sets":3,"reps":"30s","rest":"30s","key":"plank"},
        ],
        cooldown=[{"name":"Yoga Stretching","duration":"5 min"}],
    ),
    "strength_training": dict(label="Strength Training Plan",
        warmup=[{"name":"Arm Raises","sets":2,"reps":"12","rest":"20s"}],
        workout=[
            {"name":"Squat","sets":5,"reps":"5","rest":"90s","key":"squat"},
            {"name":"Push-up","sets":5,"reps":"5","rest":"90s","key":"pushup"},
            {"name":"Lunge","sets":4,"reps":"8","rest":"60s","key":"lunge"},
            {"name":"Shoulder Press","sets":4,"reps":"6","rest":"90s","key":"shoulder_press"},
        ],
        cooldown=[{"name":"Deep Stretching","duration":"8 min"}],
    ),
    "endurance_training": dict(label="Endurance Plan",
        warmup=[{"name":"High Knees","sets":2,"reps":"30s","rest":"15s"}],
        workout=[
            {"name":"Jumping Jacks","sets":4,"reps":"30","rest":"20s","key":"jumping_jacks"},
            {"name":"High Knees","sets":4,"reps":"45s","rest":"20s","key":"high_knees"},
            {"name":"Lunge","sets":3,"reps":"15","rest":"30s","key":"lunge"},
            {"name":"Squat","sets":3,"reps":"20","rest":"30s","key":"squat"},
        ],
        cooldown=[{"name":"Light Jog & Stretch","duration":"5 min"}],
    ),
    "hiit": dict(label="HIIT Conditioning Plan",
        warmup=[{"name":"Jumping Jacks","sets":1,"reps":"20","rest":"10s"}],
        workout=[
            {"name":"High Knees","sets":4,"reps":"30s","rest":"15s","key":"high_knees"},
            {"name":"Jumping Jacks","sets":4,"reps":"20","rest":"15s","key":"jumping_jacks"},
            {"name":"Squat","sets":4,"reps":"15","rest":"20s","key":"squat"},
            {"name":"Push-up","sets":3,"reps":"10","rest":"20s","key":"pushup"},
            {"name":"Plank","sets":3,"reps":"30s","rest":"15s","key":"plank"},
        ],
        cooldown=[{"name":"Walk & Stretch","duration":"5 min"}],
    ),
    "core_strength": dict(label="Core Strength Plan",
        warmup=[{"name":"Arm Raises","sets":1,"reps":"10","rest":"15s"}],
        workout=[
            {"name":"Plank","sets":4,"reps":"45s","rest":"30s","key":"plank"},
            {"name":"Side Lunge","sets":3,"reps":"12","rest":"30s","key":"side_lunge"},
            {"name":"Squat","sets":3,"reps":"12","rest":"30s","key":"squat"},
            {"name":"Push-up","sets":3,"reps":"12","rest":"30s","key":"pushup"},
        ],
        cooldown=[{"name":"Core Stretch","duration":"5 min"}],
    ),
    "senior_fitness": dict(label="Senior Fitness Plan",
        warmup=[{"name":"Arm Raises","sets":1,"reps":"8","rest":"30s"}],
        workout=[
            {"name":"Squat","sets":2,"reps":"8","rest":"60s","key":"squat"},
            {"name":"Lunge","sets":2,"reps":"6","rest":"60s","key":"lunge"},
            {"name":"Arm Raises","sets":2,"reps":"10","rest":"45s","key":"arm_raises"},
            {"name":"Plank","sets":2,"reps":"15s","rest":"45s","key":"plank"},
        ],
        cooldown=[{"name":"Gentle Stretching","duration":"10 min"}],
    ),
}

def get_plan(goal, age=25):
    """Get workout plan for goal, with fallbacks."""
    direct = {
        "fat_loss":            "weight_loss",
        "body_toning":         "weight_loss",
        "lean_muscle":         "muscle_gain",
        "calisthenics":        "muscle_gain",
        "advanced_training":   "strength_training",
        "athletic_performance":"strength_training",
        "sports_performance":  "hiit",
        "speed_agility":       "hiit",
        "stamina":             "endurance_training",
        "cardio_fitness":      "endurance_training",
        "flexibility_mobility":"general_fitness",
        "posture_improvement": "core_strength",
        "balance_stability":   "core_strength",
        "functional_fitness":  "general_fitness",
        "home_workout":        "general_fitness",
        "rehabilitation":      "senior_fitness",
        "beginner_fitness":    "general_fitness",
    }
    key = direct.get(goal, goal)
    plan = dict(PLANS.get(key, PLANS.get("general_fitness",
        dict(label="General Fitness Plan",
             warmup=[{"name":"Arm Raises","sets":2,"reps":"12","rest":"20s"}],
             workout=[
                {"name":"Squat","sets":3,"reps":"12","rest":"45s","key":"squat"},
                {"name":"Lunge","sets":2,"reps":"10","rest":"45s","key":"lunge"},
                {"name":"Push-up","sets":3,"reps":"8","rest":"45s","key":"pushup"},
                {"name":"Arm Raises","sets":3,"reps":"12","rest":"30s","key":"arm_raises"},
                {"name":"Plank","sets":3,"reps":"20s","rest":"30s","key":"plank"},
             ],
             cooldown=[{"name":"Light Stretching","duration":"5 min"}],
        ))))
    # Adjust for age
    if age and int(age) > 55:
        for ex in plan.get('workout', []):
            ex['sets'] = max(2, ex.get('sets', 3) - 1)
    return plan

PLANS["general_fitness"] = dict(
    label="General Fitness Plan",
    warmup=[{"name":"Arm Raises","sets":2,"reps":"12","rest":"20s"}],
    workout=[
        {"name":"Squat","sets":3,"reps":"12","rest":"45s","key":"squat"},
        {"name":"Lunge","sets":2,"reps":"10","rest":"45s","key":"lunge"},
        {"name":"Push-up","sets":3,"reps":"8","rest":"45s","key":"pushup"},
        {"name":"Arm Raises","sets":3,"reps":"12","rest":"30s","key":"arm_raises"},
        {"name":"Plank","sets":3,"reps":"20s","rest":"30s","key":"plank"},
    ],
    cooldown=[{"name":"Light Stretching","duration":"5 min"}],
)

GOAL_RECS = {
    "weight_loss":        ["Jumping Jacks","High Knees","Squat","Lunge","Push-up"],
    "muscle_gain":        ["Squat","Push-up","Bicep Curl","Shoulder Press","Side Lunge"],
    "body_recomposition": ["Squat","Push-up","Bicep Curl","Jumping Jacks","Plank"],
    "strength_training":  ["Squat","Push-up","Lunge","Shoulder Press","Plank"],
    "endurance_training": ["High Knees","Jumping Jacks","Lunge","Squat","Plank"],
    "hiit":               ["High Knees","Jumping Jacks","Squat","Push-up","Plank"],
    "core_strength":      ["Plank","Side Lunge","Squat","Push-up","Arm Raises"],
    "senior_fitness":     ["Squat","Lunge","Arm Raises","Plank","Side Lunge"],
}

def get_recs(goal):
    direct = {
        "fat_loss":"weight_loss","body_toning":"weight_loss",
        "lean_muscle":"muscle_gain","calisthenics":"muscle_gain",
        "advanced_training":"strength_training","athletic_performance":"strength_training",
        "sports_performance":"hiit","speed_agility":"hiit",
        "stamina":"endurance_training","cardio_fitness":"endurance_training",
        "flexibility_mobility":"general_fitness","posture_improvement":"core_strength",
        "balance_stability":"core_strength","functional_fitness":"general_fitness",
        "home_workout":"general_fitness","rehabilitation":"senior_fitness",
        "beginner_fitness":"general_fitness",
    }
    key = direct.get(goal, goal)
    return GOAL_RECS.get(key, ["Squat","Lunge","Push-up","Arm Raises","Plank"])

# Non-veg items to swap out for vegetarians/vegans
_NON_VEG = {"Chicken Breast","Fish","Egg whites","Chicken Breast","Chicken","Grilled Chicken","Beef"}
_VEG_SWAP = {
    "Chicken Breast":"Paneer", "Fish":"Tofu", "Egg whites":"Oats",
    "Chicken Breast":"Paneer", "Chicken":"Paneer", "Grilled Chicken":"Paneer",
}
_VEGAN_SWAP = {
    "Chicken Breast":"Tofu", "Fish":"Tofu", "Egg whites":"Oats",
    "Chicken Breast":"Tofu","Chicken":"Tofu","Grilled Chicken":"Tofu",
    "Milk":"Soy Milk","Full-fat Milk":"Soy Milk","Low-fat Milk":"Soy Milk",
    "Warm Milk":"Soy Milk","Greek Yogurt":"Coconut Yogurt",
    "Paneer":"Tofu","Eggs":"Tofu","Curd":"Coconut Yogurt",
}

def _filter_meal_text(text, diet):
    if diet == 'non_vegetarian':
        return text
    swap = _VEGAN_SWAP if diet == 'vegan' else _VEG_SWAP
    for k, v in swap.items():
        text = text.replace(k, v)
    return text

def _filter_foods(foods, diet):
    if diet == 'non_vegetarian':
        return foods
    veg_ok = {"Oats","Greek Yogurt","Coconut Yogurt","Paneer","Milk","Soy Milk",
               "Peanut Butter","Tofu","Lentils","Vegetables","Banana","Dates",
               "Rice","Nuts","Almonds"}
    if diet == 'vegan':
        vegan_ok = {"Oats","Soy Milk","Coconut Yogurt","Peanut Butter","Tofu",
                    "Lentils","Vegetables","Banana","Dates","Rice","Nuts","Almonds"}
        return [f for f in foods if f in vegan_ok] or ["Tofu","Lentils","Oats","Peanut Butter"]
    return [f for f in foods if f in veg_ok or f not in _NON_VEG] or ["Paneer","Tofu","Lentils","Oats"]

def build_diet(profile):
    w    = float(profile.get('weight', 70))
    goal = profile.get('fitness_goal', 'general_fitness')
    diet = profile.get('diet', 'non_vegetarian')
    pl   = round(w*1.6, 1); ph = round(w*2.2, 1)
    raw  = get_meals(goal)
    # Filter meals based on diet preference
    meals = dict(
        breakfast = _filter_meal_text(raw['breakfast'], diet),
        lunch     = _filter_meal_text(raw['lunch'],     diet),
        snack     = _filter_meal_text(raw['snack'],     diet),
        dinner    = _filter_meal_text(raw['dinner'],    diet),
        pre_bed   = _filter_meal_text(raw['pre_bed'],   diet),
        foods     = _filter_foods(raw.get('foods', []), diet),
    )
    label = GOAL_LABELS.get(goal, goal.replace('_',' ').title())
    return dict(protein_range=f"{pl}g – {ph}g", protein_low=pl,
                protein_high=ph, meals=meals, goal=label)

# ═══════════════════════════════════════════════════════════════════════════
# PDF GENERATION
# ═══════════════════════════════════════════════════════════════════════════

def generate_pdf(profile):
    buf  = BytesIO()
    doc  = SimpleDocTemplate(buf, pagesize=A4,
        leftMargin=2*cm, rightMargin=2*cm, topMargin=2*cm, bottomMargin=2*cm)
    styl = getSampleStyleSheet()
    W    = A4[0] - 4*cm

    def ps(name, **kw):
        return ParagraphStyle(name, parent=styl['Normal'], **kw)

    t_s  = ps('T', fontSize=22, textColor=colors.HexColor('#0066ff'),
               fontName='Helvetica-Bold', alignment=TA_CENTER, spaceAfter=4)
    su_s = ps('Su', fontSize=11, textColor=colors.HexColor('#5a5f7a'),
               alignment=TA_CENTER, spaceAfter=4)
    h_s  = ps('H', fontSize=13, fontName='Helvetica-Bold',
               textColor=colors.HexColor('#0f1117'), spaceBefore=14, spaceAfter=6)
    b_s  = ps('B', fontSize=10, textColor=colors.HexColor('#2a2d3a'),
               spaceAfter=4, leading=15)
    hl_s = ps('HL', fontSize=14, fontName='Helvetica-Bold',
               textColor=colors.HexColor('#0066ff'), alignment=TA_CENTER)
    f_s  = ps('F', fontSize=8, textColor=colors.HexColor('#9499b5'),
               alignment=TA_CENTER)

    diet  = build_diet(profile)
    plan  = get_plan(profile.get('fitness_goal','general_fitness'),
                     profile.get('age', 25))
    meals = diet['meals']
    pl, ph = diet['protein_low'], diet['protein_high']
    name   = profile.get('name','User')
    weight = profile.get('weight','—')
    age    = profile.get('age','—')
    height = profile.get('height','—')
    gender = str(profile.get('gender','—')).title()
    goal   = diet['goal']
    story  = []

    story += [
        Paragraph("Fitnova AI", t_s),
        Paragraph("AI Workout Trainer – Personal Nutrition Plan", su_s),
        HRFlowable(width=W, thickness=2, color=colors.HexColor('#0066ff'), spaceAfter=12),
        Paragraph("Personal Information", h_s),
    ]

    # User info table
    t = Table([
        ['Name', name,        'Age',    str(age)],
        ['Height', f'{height} cm', 'Weight', f'{weight} kg'],
        ['Gender', gender,    'Goal',   goal],
    ], colWidths=[W*.22, W*.28, W*.22, W*.28])
    t.setStyle(TableStyle([
        ('BACKGROUND',(0,0),(-1,-1),colors.HexColor('#f0f1f5')),
        ('BACKGROUND',(0,0),(0,-1),colors.HexColor('#e8eeff')),
        ('BACKGROUND',(2,0),(2,-1),colors.HexColor('#e8eeff')),
        ('FONTNAME',(0,0),(0,-1),'Helvetica-Bold'),
        ('FONTNAME',(2,0),(2,-1),'Helvetica-Bold'),
        ('TEXTCOLOR',(0,0),(0,-1),colors.HexColor('#0066ff')),
        ('TEXTCOLOR',(2,0),(2,-1),colors.HexColor('#0066ff')),
        ('FONTSIZE',(0,0),(-1,-1),10),
        ('GRID',(0,0),(-1,-1),.5,colors.HexColor('#e4e6ec')),
        ('PADDING',(0,0),(-1,-1),8), ('VALIGN',(0,0),(-1,-1),'MIDDLE'),
    ]))
    story += [t, Spacer(1,10)]

    # Protein
    story += [
        HRFlowable(width=W,thickness=1,color=colors.HexColor('#e4e6ec'),spaceAfter=6),
        Paragraph("Daily Protein Requirement", h_s),
        Paragraph(f"Formula: Body Weight × 1.6g – 2.2g per kg"
                  f"  →  <b>{weight} kg × 1.6–2.2 = {pl}g – {ph}g / day</b>", b_s),
    ]
    pb = Table([[Paragraph(f"{pl}g – {ph}g per day", hl_s)]], colWidths=[W])
    pb.setStyle(TableStyle([
        ('BACKGROUND',(0,0),(-1,-1),colors.HexColor('#e8eeff')),
        ('PADDING',(0,0),(-1,-1),12),
        ('BOX',(0,0),(-1,-1),1.5,colors.HexColor('#0066ff')),
    ]))
    story += [pb, Spacer(1,10)]

    # Meal plan
    story += [
        HRFlowable(width=W,thickness=1,color=colors.HexColor('#e4e6ec'),spaceAfter=6),
        Paragraph("Daily Meal Plan", h_s),
    ]
    mrows = [[Paragraph('<b>Meal</b>',b_s), Paragraph('<b>Food</b>',b_s)]]
    for lbl, content in [
        ('Breakfast', meals['breakfast']),('Lunch', meals['lunch']),
        ('Snack',       meals['snack']),    ('Dinner',    meals['dinner']),
        ('Before Bed',meals['pre_bed']),
    ]:
        mrows.append([Paragraph(lbl,b_s), Paragraph(content,b_s)])
    mt = Table(mrows, colWidths=[W*.28, W*.72])
    mt.setStyle(TableStyle([
        ('BACKGROUND',(0,0),(-1,0),colors.HexColor('#0066ff')),
        ('TEXTCOLOR',(0,0),(-1,0),colors.white),
        ('FONTNAME',(0,0),(-1,0),'Helvetica-Bold'),
        ('FONTSIZE',(0,0),(-1,-1),10),
        ('ROWBACKGROUNDS',(0,1),(-1,-1),[colors.HexColor('#f7f8fa'),colors.white]),
        ('GRID',(0,0),(-1,-1),.5,colors.HexColor('#e4e6ec')),
        ('PADDING',(0,0),(-1,-1),9), ('VALIGN',(0,0),(-1,-1),'MIDDLE'),
    ]))
    story += [mt, Spacer(1,10)]

    # Workout plan
    story += [
        HRFlowable(width=W,thickness=1,color=colors.HexColor('#e4e6ec'),spaceAfter=6),
        Paragraph(f"Workout Plan: {plan['label']}", h_s),
    ]
    wrows = [[Paragraph('<b>Exercise</b>',b_s), Paragraph('<b>Sets</b>',b_s),
              Paragraph('<b>Reps</b>',b_s),    Paragraph('<b>Rest</b>',b_s)]]
    for ex in plan['workout']:
        wrows.append([Paragraph(ex['name'],b_s), Paragraph(str(ex['sets']),b_s),
                      Paragraph(str(ex['reps']),b_s), Paragraph(ex.get('rest','30s'),b_s)])
    wt = Table(wrows, colWidths=[W*.40, W*.15, W*.25, W*.20])
    wt.setStyle(TableStyle([
        ('BACKGROUND',(0,0),(-1,0),colors.HexColor('#0066ff')),
        ('TEXTCOLOR',(0,0),(-1,0),colors.white),
        ('FONTNAME',(0,0),(-1,0),'Helvetica-Bold'),
        ('FONTSIZE',(0,0),(-1,-1),10),
        ('ROWBACKGROUNDS',(0,1),(-1,-1),[colors.HexColor('#f7f8fa'),colors.white]),
        ('GRID',(0,0),(-1,-1),.5,colors.HexColor('#e4e6ec')),
        ('PADDING',(0,0),(-1,-1),9), ('VALIGN',(0,0),(-1,-1),'MIDDLE'),
    ]))
    story += [wt, Spacer(1,10)]

    # Protein foods
    story += [
        HRFlowable(width=W,thickness=1,color=colors.HexColor('#e4e6ec'),spaceAfter=6),
        Paragraph("Recommended High-Protein Foods", h_s),
    ]
    fl = meals.get('foods', [])
    rows_f = [fl[i:i+3] for i in range(0, len(fl), 3)]
    while rows_f and len(rows_f[-1]) < 3: rows_f[-1].append('')
    ft = Table(
        [[Paragraph(f"• {f}" if f else '', b_s) for f in row] for row in rows_f],
        colWidths=[W/3]*3)
    ft.setStyle(TableStyle([
        ('BACKGROUND',(0,0),(-1,-1),colors.HexColor('#f0fff8')),
        ('GRID',(0,0),(-1,-1),.5,colors.HexColor('#d0f0e0')),
        ('PADDING',(0,0),(-1,-1),8),
        ('TEXTCOLOR',(0,0),(-1,-1),colors.HexColor('#007a50')),
    ]))
    story += [ft, Spacer(1,10)]

    story += [
        HRFlowable(width=W,thickness=1,color=colors.HexColor('#e4e6ec'),spaceAfter=6),
        Paragraph("Generated by Fitnova AI – AI Personal Trainer Platform  |  fitnova.ai", f_s),
    ]
    doc.build(story)
    buf.seek(0)
    return buf

# ═══════════════════════════════════════════════════════════════════════════
# FLASK ROUTES
# ═══════════════════════════════════════════════════════════════════════════

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/profile')
def profile():
    return render_template('profile.html')

@app.route('/api/goals')
def api_goals():
    return jsonify({'goals': ALL_GOALS})

@app.route('/api/process_frame', methods=['POST'])
def process_frame():
    if not CV_OK:
        return jsonify({'error': 'Computer vision not available', 'feedback': 'CV not ready', 'reps': 0, 'form_ok': False})
    try:
        data = request.json
        b64  = data.get('frame','')
        ex   = data.get('exercise','squat')
        sid  = data.get('session_id','default')

        if ',' in b64: b64 = b64.split(',')[1]
        img = np.frombuffer(base64.b64decode(b64), dtype=np.uint8)
        frame = cv2.imdecode(img, cv2.IMREAD_COLOR)
        if frame is None: return jsonify({'error':'Invalid frame'}), 400

        ph = 480
        frame = cv2.resize(frame, (int(frame.shape[1]*ph/frame.shape[0]), ph))
        res = pose_detector.process(cv2.cvtColor(frame, cv2.COLOR_BGR2RGB))

        if not res.pose_landmarks:
            cv2.putText(frame,"Position yourself – full body visible",
                (20,frame.shape[0]//2),cv2.FONT_HERSHEY_SIMPLEX,0.7,(200,200,200),2,cv2.LINE_AA)
            _,enc=cv2.imencode('.jpg',frame,[cv2.IMWRITE_JPEG_QUALITY,78])
            return jsonify(dict(detected=False,
                feedback='Position yourself so your full body is visible.',
                reps=0,angle=0,form_ok=False,accuracy=0,
                correct_reps=0,wrong_reps=0,mistakes=[],
                processed_frame='data:image/jpeg;base64,'+base64.b64encode(enc).decode()))

        L   = res.pose_landmarks.landmark
        st  = get_ex(sid, ex)
        fb, ok, acc = DETECTORS.get(ex, det_squat)(L, st)

        st['form_acc_sum'] += acc; st['form_checks'] += 1
        dash = get_dash(sid)
        if acc > 0: dash['acc_sum'] += acc; dash['acc_cnt'] += 1

        frame = draw_skeleton(frame, res.pose_landmarks, ok)
        frame = add_hud(frame, ex, st['reps'], st['last_angle'], ok, acc, fb)

        _,enc = cv2.imencode('.jpg',frame,[cv2.IMWRITE_JPEG_QUALITY,82])
        return jsonify(dict(detected=True, feedback=fb,
            reps=st['reps'], angle=st['last_angle'],
            form_ok=ok, accuracy=acc,
            correct_reps=st['correct_reps'], wrong_reps=st['wrong_reps'],
            mistakes=st['mistakes'][-3:],
            processed_frame='data:image/jpeg;base64,'+base64.b64encode(enc).decode()))
    except Exception as e:
        import traceback; traceback.print_exc()
        return jsonify({'error': str(e)}), 500

@app.route('/api/reset_exercise', methods=['POST'])
def reset_exercise():
    d = request.json
    key = f"{d.get('session_id','default')}_{d.get('exercise','squat')}"
    if key in ex_state: del ex_state[key]
    return jsonify({'status':'reset'})

@app.route('/api/get_summary', methods=['POST'])
def get_summary():
    d   = request.json
    key = f"{d.get('session_id','default')}_{d.get('exercise','squat')}"
    st  = ex_state.get(key,{})
    reps=st.get('reps',0); corr=st.get('correct_reps',0)
    acc = round(corr/reps*100,1) if reps>0 else 0
    return jsonify(dict(exercise=d.get('exercise','squat'),
        total_reps=reps, correct_reps=corr, wrong_reps=st.get('wrong_reps',0),
        accuracy=acc, mistakes=list(set(st.get('mistakes',[])))))

@app.route('/api/save_profile', methods=['POST'])
def save_profile():
    p = request.json
    if not p: return jsonify({'error':'No data'}), 400
    session['profile'] = p
    # Store per unique session — Flask session cookie isolates per browser automatically
    diet = build_diet(p)
    plan = get_plan(p.get('fitness_goal','general_fitness'), p.get('age',25))
    recs = get_recs(p.get('fitness_goal','general_fitness'))
    return jsonify(dict(status='saved', diet=diet, plan=plan, recommendations=recs))

@app.route('/api/get_profile')
def get_profile_api():
    p = session.get('profile', {})
    if not p: return jsonify({'profile': None})
    diet = build_diet(p)
    plan = get_plan(p.get('fitness_goal','general_fitness'), p.get('age',25))
    recs = get_recs(p.get('fitness_goal','general_fitness'))
    return jsonify(dict(profile=p, diet=diet, plan=plan, recommendations=recs))

@app.route('/api/get_daily_plan', methods=['POST'])
def get_daily_plan():
    p = request.json or session.get('profile',{})
    if not p: return jsonify({'error':'No profile'}), 400
    return jsonify(dict(plan=get_plan(p.get('fitness_goal','general_fitness'), p.get('age',25)),
                        diet=build_diet(p)))

@app.route('/api/dashboard_stats')
def dashboard_stats():
    sid  = request.args.get('session_id','default')
    dash = get_dash(sid)
    exs  = []
    for key, st in ex_state.items():
        if not key.startswith(sid): continue
        parts = key.split('_',1)
        if len(parts)<2: continue
        reps=st.get('reps',0)
        if reps>0:
            c=st.get('form_checks',1) or 1
            exs.append(dict(exercise=parts[1].replace('_',' ').title(),
                reps=reps, correct=st.get('correct_reps',0),
                accuracy=round(st.get('form_acc_sum',0)/c,1),
                mistakes=list(set(st.get('mistakes',[])))))
    total = sum(e['reps'] for e in exs)
    acc   = round(dash['acc_sum']/dash['acc_cnt'],1) if dash['acc_cnt'] else 0
    return jsonify(dict(workouts_completed=len([e for e in exs if e['reps']>=5]),
        total_reps=total, overall_accuracy=acc, exercises=exs))

@app.route('/api/workout_history')
def workout_history():
    hist = []
    for key, st in ex_state.items():
        parts = key.split('_',1)
        if len(parts)==2 and st.get('reps',0)>0:
            c=st.get('form_checks',1) or 1
            hist.append(dict(exercise=parts[1], reps=st['reps'],
                accuracy=round(st.get('form_acc_sum',0)/c,1),
                mistakes=list(set(st.get('mistakes',[])))))
    return jsonify({'history': hist})

@app.route('/api/download_nutrition_pdf', methods=['POST'])
def download_nutrition_pdf():
    if not REPORTLAB_OK:
        return jsonify({'error':'reportlab not installed on server'}), 500
    profile = request.json or session.get('profile',{})
    if not profile: return jsonify({'error':'No profile data'}), 400
    try:
        buf = generate_pdf(profile)
        return send_file(buf, mimetype='application/pdf', as_attachment=True,
                         download_name='nutrition_plan.pdf')
    except Exception as e:
        import traceback; traceback.print_exc()
        return jsonify({'error': str(e)}), 500

@app.route('/download-nutrition-pdf', methods=['POST'])
def download_nutrition_pdf_alt():
    """Alternative endpoint as per spec: /download-nutrition-pdf"""
    if not REPORTLAB_OK:
        return jsonify({'error':'reportlab not installed on server'}), 500
    profile = request.json or session.get('profile',{})
    if not profile: return jsonify({'error':'No profile data'}), 400
    try:
        buf = generate_pdf(profile)
        return send_file(buf, mimetype='application/pdf', as_attachment=True,
                         download_name='nutrition_plan.pdf')
    except Exception as e:
        import traceback; traceback.print_exc()
        return jsonify({'error': str(e)}), 500

import admin_module
admin_module.register(app)

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=False)
