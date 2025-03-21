# _*_ coding: utf-8 _*_
# @Time : 2024/12/10
# @Author : Tech_T

import sqlite3
import time
import re
from datetime import datetime
from sendqueue import QueueDB
from config.log import LogConfig

log = LogConfig().get_logger()


def send_remind(tips, receiver, produce = 'homework'):
    mid = str(time.time().__int__())
    with QueueDB() as q:
        q.send_text(mid, tips, receiver, '', produce)
    time.sleep(1)


class Homework:
    def __init__(self):
        self.subjects = ['语文', '数学', '英语', '物理', '化学', '生物', '地理', '历史', '政治', '美术','技术', '班级']
    def __enter__(self, db_path='databases/homework.db'):
        self.db_path = db_path
        self.conn = sqlite3.connect(self.db_path)
        self.cursor = self.conn.cursor()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.conn.close()

    def __create_table__(self):
        try:
            self.cursor.execute("""
            CREATE TABLE IF NOT EXISTS homework (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                class_code INTEGER,
                subject TEXT,
                teacher TEXT,
                content TEXT,
                deadline TEXT,
                assigned_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                status BOOLEAN DEFAULT 0,
                duration INTEGER,
                type TEXT,
                wxid TEXT
            )
            """)
            self.conn.commit()
            log.info('表：homework 创建成功')
        except sqlite3.OperationalError as e:
            if 'already exists' in str(e):
                log.info('表：homework 已存在, 跳过创建')
            else:
                log.error('表：homework 创建失败')
                raise e

        try:
            self.cursor.execute("""
            CREATE TABLE IF NOT EXISTS announcements (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                class_code INTEGER,
                title TEXT,
                author TEXT,
                content TEXT,
                date DATETIME DEFAULT CURRENT_TIMESTAMP,
                wxid TEXT
            )
            """)
            self.conn.commit()
            log.info('表：announcements 创建成功')
        except sqlite3.OperationalError as e:
            if 'already exists' in str(e):
                log.info('表：announcements 已存在, 跳过创建')
            else:
                log.error('表：announcements 创建失败')
                raise e
        

    def add_homework(self, class_code, subject, teacher, content, deadline, duration, type, wxid):
        try:
            self.cursor.execute("""
            INSERT INTO homework (class_code, subject, teacher, content, deadline, duration, type, wxid)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, (class_code, subject, teacher, content, deadline, duration, type, wxid))
            self.conn.commit()
        except sqlite3.IntegrityError as e:
            log.error('作业添加失败')
            raise e

        return self.cursor.lastrowid

    def get_homework(self, class_code, subject, type='日常'):
        try:
            # self.cursor.execute("""
            # SELECT * FROM homework WHERE type = ? AND subject = ? AND class_code = ? order by id desc limit 1
            # """, (type, subject, class_code))
            self.cursor.execute("""SELECT * FROM homework WHERE class_code = ? AND subject = ? AND type = ? order by id desc limit 1""", (class_code, subject, type))
            row =  self.cursor.fetchone()
            if row:
                deadline = time.mktime(time.strptime(row[5], "%Y-%m-%d"))
                now = time.mktime(time.localtime())
                if now < deadline:
                    return {
                        'id': row[0],
                        'subject': row[2],
                        'teacher': row[3],
                        'content': row[4],
                        'deadline': row[5],
                        'assigned_date': row[6][:10],
                        'status': row[7],
                        'duration': row[8],
                        'type': row[9]
                    }
                else:
                    return None
            else:
                return None
        except sqlite3.OperationalError as e:
            log.error('获取作业失败')
            raise e

    def add_announcement(self, class_code, title, author, content, wxid):
        try:
            self.cursor.execute("""
            INSERT INTO announcements (class_code, title, author, content, wxid)
            VALUES (?, ?, ?, ?, ?)
            """, (class_code, title, author, content, wxid))
            self.conn.commit()
        except sqlite3.IntegrityError as e:
            log.error('公告添加失败')
            raise e

    def get_announcement(self, class_code):
        try:
            self.cursor.execute("""
            SELECT * FROM announcements WHERE class_code = ? order by id desc limit 5
            """, (class_code,))
            rows =  self.cursor.fetchall()
            if rows:
                announcements = []
                for row in rows:
                    announcements.append({
                        'id': row[0],
                        'title': row[2],
                        'author': row[3],
                        'content': row[4],
                        'date': row[5]
                    })
                return announcements
            else:
                return []
        except sqlite3.OperationalError as e:
            log.error('获取公告失败')
            raise e


async def incert_homework(record):
    """
    record.content='作业布置\n$班级：202401/202402\n$学科：地理\n$教师：李老师\n$内容：\n1.完成学案\n2.预习新课\n3.练习\n$上交日期：2024-12-12\n$预计用时：20\n$ 作业类型：日常'
    """
    content = re.sub(r'(\n+)', '\n', record.content)
    content = re.sub(r':', '：', content)
    contents = content.split('$')
    new_contents = []
    for i in range(1, len(contents)):
        temp = re.sub(r'\n+$', '', contents[i])
        new_contents.append(temp)
    if len(new_contents) == 7:
        class_code = new_contents[0][3:]
        subject = new_contents[1][3:]
        teacher = new_contents[2][3:]
        content = new_contents[3][3:]
        deadline = new_contents[4][5:]
        duration = int(new_contents[5][5:]) if new_contents[5][5:].isdigit() else new_contents[5][5:]
        type = new_contents[6][5:]
        try:
            # 指定日期格式
            datetime.strptime(deadline, '%Y-%m-%d')
            n = Homework()
            n.__enter__()
            classes = class_code.split('/')
            for c in classes:
                n.add_homework(c, subject, teacher, content, deadline, duration, type, record.roomid)
            send_remind(f'作业已布置：{class_code} {subject} {teacher} {content} {deadline} {duration} {type}', record.roomid)
        except ValueError:
            send_remind("作业上交日期格式不正确", record.roomid)
        
    else:
        send_remind('作业布置失败，请检查格式', record.roomid)

async def get_class_homework(record):
    """
    record.content='202401日常作业'
    """
    class_code = record.content[0:6]
    type = record.content[6:8]
    n = Homework()
    n.__enter__()
    homework = f"{class_code} {type}作业:"
    for subject in n.subjects:
        subject_homework = n.get_homework(class_code, subject, type)
        if subject_homework:
            homework += f"\n{subject_homework['subject']}: {subject_homework['content']}"
    send_remind(homework, record.roomid)
    n.__exit__(None, None, None)

async def incert_announcement(record):
    content = re.sub(r'(\n+)', '\n', record.content)
    content = re.sub(r':', '：', content)
    contents = content.split('$')
    new_contents = []
    for i in range(1, len(contents)):
        temp = re.sub(r'\n+$', '', contents[i])
        new_contents.append(temp)
    if len(new_contents) == 4:
        class_code = new_contents[0][3:]
        title = new_contents[1][3:]
        author = new_contents[2][3:]
        content = new_contents[3][3:]
        n = Homework()
        n.__enter__()
        classes = class_code.split('/')
        for c in classes:
            n.add_announcement(c, title, author, content, record.roomid)
        send_remind(f'公告已发布：{class_code} {title} {author} {content}', record.roomid)
    else:
        send_remind('公告发布失败，请检查格式', record.roomid)