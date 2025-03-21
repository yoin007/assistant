from operator import ne
from turtle import st
from fastapi import APIRouter, HTTPException, Depends
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from datetime import datetime
import pandas as pd
import os

from requests import get

from function.lesson.lesson import Lesson
from function.lesson.homework import Homework
router = APIRouter()


def get_schedule_data(next_week:bool=False):
    weekdays = {
    '1': 'monday',
    '2': 'tuesday',
    '3': 'wednesday',
    '4': 'thursday',
    '5': 'friday'
    }
    l = Lesson()
    class_template = l.class_template
    # print(class_template)
    schedule_file = l.current_schedule_file(next_week)
    # print(schedule_file)
    df_schedule_original = pd.read_excel(schedule_file, engine='openpyxl')
    df_schedule = l.format_schedule(df_schedule_original, week_next=next_week)
    schedule_data = {}
    for class_name in df_schedule.columns[4:]:
        if class_name not in class_template['class_name'].tolist():
            continue
        class_code = str(class_template[class_template['class_name'] == class_name]['class_code'].values[0])
        schedule_data[class_code] = {}
        for week, group in df_schedule[[class_name, 'week']].groupby('week'):
            schedule_data[class_code][weekdays[str(week)]] = group[class_name].tolist()
    return schedule_data

SCHEDULE_DATA = get_schedule_data()
CLASS_LIST = list(SCHEDULE_DATA.keys())

def get_teacher_data():
    l = Lesson()
    subject_teacher = pd.read_excel(os.path.join(l.lesson_dir, 'checkTemplate.xlsx'), sheet_name='teachers', engine='openpyxl')
    teachers_data = {}
    for teacher in subject_teacher['name'].tolist():
        teachers_data[teacher] = subject_teacher[subject_teacher['name'] == teacher]['subject'].values[0].split('/')
    return teachers_data

TEACHERS_DATA = get_teacher_data()

def get_time_table():
    l = Lesson()
    time_table = {}
    for index, row in l.time_table.iterrows():
        order = row['label']
        time_table[order] = row['show_time']
    return time_table

PERIODS = get_time_table()

# 作息时间
# PERIODS = {
#     "早读": "07:30-08:00",
# }


# 模拟不同班级的班主任寄语数据
TEACHER_MESSAGES = {
    "202401": {
        "content": "亲爱的同学们，在新的学期里，希望大家能够以饱满的热情投入学习。记住，成功不是偶然的，而是来自于每一天的积累和努力。让我们携手共创一个积极向上、团结互助的班级氛围！",
        "teacher": "张明",
        "date": "2024-12-08"
    }
}

from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from typing import Optional
from datetime import datetime, timedelta
import jwt
from pydantic import BaseModel

# JWT配置
SECRET_KEY = "your-secret-key"  # 在实际应用中应该使用环境变量
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 30000

def get_user_data():
    l = Lesson()
    subject_teacher = pd.read_excel(os.path.join(l.lesson_dir, 'checkTemplate.xlsx'), sheet_name='teachers', engine='openpyxl')
    users_data = {}
    for teacher in subject_teacher['name'].tolist():
        users_data[teacher] = {}
        users_data[teacher]['username'] = teacher
        users_data[teacher]['hashed_password'] = str(subject_teacher[subject_teacher['name'] == teacher]['pwd'].values[0])
        users_data[teacher]['role'] = 'teacher'
    return users_data

# 用户数据
USERS_DATA = get_user_data()

# 认证相关模型
class Token(BaseModel):
    access_token: str
    token_type: str

class TokenData(BaseModel):
    username: Optional[str] = None

class User(BaseModel):
    username: str
    role: str

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="token")

# 认证相关函数
def verify_password(plain_password, hashed_password):
    return plain_password == hashed_password

def get_user(username: str):
    if username in USERS_DATA:
        user_dict = USERS_DATA[username]
        return User(username=user_dict["username"], role=user_dict["role"])
    return None

def authenticate_user(username: str, password: str):
    if username not in USERS_DATA:
        return False
    user = USERS_DATA[username]
    if not verify_password(password, user["hashed_password"]):
        return False
    return user

def create_access_token(data: dict, expires_delta: Optional[timedelta] = None):
    to_encode = data.copy()
    if expires_delta:
        expire = datetime.utcnow() + expires_delta
    else:
        expire = datetime.utcnow() + timedelta(minutes=15)
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
    return encoded_jwt

async def get_current_user(token: str = Depends(oauth2_scheme)):
    credentials_exception = HTTPException(
        status_code=401,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        username: str = payload.get("sub")
        if username is None:
            raise credentials_exception
        token_data = TokenData(username=username)
    except jwt.PyJWTError:
        raise credentials_exception
    user = get_user(username=token_data.username)
    if user is None:
        raise credentials_exception
    return user

# 登录接口
@router.post("/token")
async def login_for_access_token(form_data: OAuth2PasswordRequestForm = Depends()):
    user = authenticate_user(form_data.username, form_data.password)
    if not user:
        raise HTTPException(
            status_code=401,
            detail="Incorrect username or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    access_token_expires = timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    access_token = create_access_token(
        data={"sub": user["username"]}, expires_delta=access_token_expires
    )
    return {"access_token": access_token, "token_type": "bearer"}

# 获取所有班级代码
@router.get("/class-codes")
async def get_class_codes():
    """获取所有可用的班级代码"""
    return {"class_codes": list(SCHEDULE_DATA.keys())}

@router.get("/schedule/{class_code}")
async def get_class_schedule(class_code: str):
    """获取指定班级的课程表"""
    if class_code not in SCHEDULE_DATA:
        raise HTTPException(status_code=404, detail="未找到该班级的课程表")
    return {"schedule": SCHEDULE_DATA[class_code]}

@router.get("/homework/{class_code}")
async def get_homework(class_code: str):
    """获取作业列表，按类型分类并过滤过期作业"""
    n = Homework()
    n.__enter__()
    subjects = n.subjects
    homework_data = []
    for subject in subjects:
        daily = n.get_homework(class_code, subject, '日常')
        weekly = n.get_homework(class_code, subject, '周末')
        if daily and weekly:
            homework_data.append(daily)
            homework_data.append(weekly)
        elif daily:
            homework_data.append(daily)
        elif weekly:
            homework_data.append(weekly)
    n.__exit__(None, None, None)
    # if class_code not in HOMEWORK_DATA:
    #     return {"daily": [], "weekly": []}

    current_date = datetime.now().strftime("%Y-%m-%d")
    
    # 按类型分类作业
    homework_by_type = {"日常": [], "周末": []}
    teacher_latest = {}  # 用于记录每个老师最新的作业
    
    # 首先按时间排序
    sorted_homework = sorted(
        homework_data,
        key=lambda x: (x["assigned_date"], x["deadline"]),
        reverse=True
    )
    
    # 过滤和分类作业
    for hw in sorted_homework:
        # 跳过已过期的作业
        if hw["deadline"] < current_date:
            continue
            
        # 为每个老师的每种类型只保留最新的作业
        teacher_key = f"{hw['teacher']}_{hw['type']}"
        if teacher_key not in teacher_latest:
            teacher_latest[teacher_key] = hw
            homework_by_type[hw["type"]].append(hw)
    
    return homework_by_type

@router.get("/announcements/{class_code}")
async def get_class_announcements(class_code: str):
    """获取指定班级的公告"""
    n = Homework()
    n.__enter__()
    announcements = n.get_announcement(class_code)
    return {"announcements": announcements}

@router.get("/messages/{class_code}")
async def get_teacher_messages(class_code: str):
    """获取指定班级的老师留言"""
    if class_code not in TEACHER_MESSAGES:
        return {"messages": []}
    return {"messages": [TEACHER_MESSAGES[class_code]]}

@router.get("/class-info/{class_code}")
async def get_class_info(class_code: str):
    """获取指定班级的基本信息"""
    l = Lesson()
    class_template = l.class_template[l.class_template['class_code'] == int(class_code)].iloc[0].to_dict()
    class_info = {
        "className": class_template['class_name'],
        "classTeacher": class_template['leaders'],
        "studentCount": class_template['studentCount'],
        "established": class_template['established'],
        "motto": class_template['motto'],
        "location": class_template['location'],
    }
    return {"class_info": class_info}

@router.get("/students/{class_code}")
async def get_students(class_code: str):
    """获取指定班级的学生名单"""
    l = Lesson()
    student_template_file = os.path.join(l.lesson_dir, 'students.xlsx')
    student_template = pd.read_excel(student_template_file, sheet_name=str(class_code))
    students = student_template['name'].to_list()
    return {"students": students}

@router.get("/periods")
async def get_periods():
    """获取课程时间安排"""
    return {"periods": PERIODS}

@router.get("/current-classes", dependencies=[Depends(get_current_user)])
async def get_current_classes():
    """获取当前所有班级正在上的课程"""
    current_time = datetime.now().strftime("%H:%M")
    current_classes = {}
    
    for class_code, schedule in SCHEDULE_DATA.items():
        current_period = None
        
        for period, time_range in PERIODS.items():
            print(period, time_range)
            start_time, end_time = time_range.split("-")
            # 将时间字符串转换为分钟数，以便进行比较
            start_minutes = sum(int(x) * 60 ** i for i, x in enumerate(reversed(start_time.split(":"))))
            print(start_minutes)
            end_minutes = sum(int(x) * 60 ** i for i, x in enumerate(reversed(end_time.split(":"))))
            current_minutes = sum(int(x) * 60 ** i for i, x in enumerate(reversed(current_time.split(":"))))
            
            if start_minutes <= current_minutes <= end_minutes:
                current_period = period
                break
        if current_period is not None:
            # 获取当前是星期几
            weekday = datetime.now().weekday()
            weekday_map = {
                0: "monday",
                1: "tuesday",
                2: "wednesday",
                3: "thursday",
                4: "friday"
            }
            
            if weekday in weekday_map:  # 周一到周五
                day_name = weekday_map[weekday]
                day_schedule = schedule.get(day_name, [])
                period_index = list(PERIODS.keys()).index(current_period)
                
                if 0 <= period_index < len(day_schedule):
                    subject = day_schedule[period_index]
                    # 根据科目查找对应的教师
                    teacher = None
                    for t, subjects in TEACHERS_DATA.items():
                        if subject in subjects:
                            teacher = t
                            break
                    
                    current_classes[class_code] = {
                        "subject": subject,
                        "teacher": teacher or "未知教师",
                        "period": current_period
                    }
    
    return {"current_classes": current_classes}

@router.get("/teacher-schedule/{teacher_name}", dependencies=[Depends(get_current_user)])
async def get_teacher_schedule(teacher_name: str):
    """获取指定教师的课表"""
    if teacher_name not in TEACHERS_DATA:
        raise HTTPException(status_code=404, detail="教师不存在")
    
    teacher_subjects = TEACHERS_DATA[teacher_name]
    teacher_schedule = {str(i): {} for i in range(1, 6)}  # 周一到周五
    weekday_map = {
        "monday": "1",
        "tuesday": "2",
        "wednesday": "3",
        "thursday": "4",
        "friday": "5"
    }
    
    schedule_data = get_schedule_data()
    
    for class_code, schedule in schedule_data.items():
        for day_name, day_schedule in schedule.items():
            day_number = weekday_map.get(day_name)
            if day_number:
                for period_index, subject in enumerate(day_schedule):
                    if subject in teacher_subjects:
                        period = list(PERIODS.keys())[period_index]
                        if period not in teacher_schedule[day_number]:
                            teacher_schedule[day_number][period] = []
                        teacher_schedule[day_number][period].append({
                            "class_code": class_code,
                            "subject": subject
                        })
    
    return {"schedule": teacher_schedule}

@router.get("/teacher-schedule-nextweek/{teacher_name}", dependencies=[Depends(get_current_user)])
async def get_teacher_schedule_nextweek(teacher_name: str):
    """获取指定教师的课表"""
    if teacher_name not in TEACHERS_DATA:
        raise HTTPException(status_code=404, detail="教师不存在")
    
    teacher_subjects = TEACHERS_DATA[teacher_name]
    teacher_schedule = {str(i): {} for i in range(1, 6)}  # 周一到周五
    weekday_map = {
        "monday": "1",
        "tuesday": "2",
        "wednesday": "3",
        "thursday": "4",
        "friday": "5"
    }
    
    schedule_data = get_schedule_data(next_week=True)
    # print(schedule_data)
    
    for class_code, schedule in schedule_data.items():
        for day_name, day_schedule in schedule.items():
            day_number = weekday_map.get(day_name)
            if day_number:
                for period_index, subject in enumerate(day_schedule):
                    if subject in teacher_subjects:
                        period = list(PERIODS.keys())[period_index]
                        if period not in teacher_schedule[day_number]:
                            teacher_schedule[day_number][period] = []
                        teacher_schedule[day_number][period].append({
                            "class_code": class_code,
                            "subject": subject
                        })
    
    return {"schedule": teacher_schedule}

@router.get("/teachers", dependencies=[Depends(get_current_user)])
async def get_teachers():
    """获取所有教师列表"""
    return {"teachers": list(TEACHERS_DATA.keys())}
