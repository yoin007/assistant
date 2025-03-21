# _*_ coding :utf-8 _*_
# @Time : 2024/11/4 20:56
# @Author : Tech_T

import re
import sqlite3
import time

from sendqueue import QueueDB

from config.config import Config
from config.log import LogConfig

config = Config()
log = LogConfig().get_logger()

def send_remind(tips, receiver, produce = 'notes'):
    mid = str(time.time().__int__())
    with QueueDB() as q:
        q.send_text(mid, tips, receiver, '', produce)
    time.sleep(1)

class Notes:
    def __enter__(self, db='databases/notes.db'):
        self.__conn__ = sqlite3.connect(db)
        self.__cursor__ = self.__conn__.cursor()
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        self.__conn__.close()

    def __create_table__(self):
        try:
            self.__cursor__.execute("""
            CREATE TABLE notes(
            id INTEGER PRIMARY KEY,
            teacher TEXT,
            note TEXT,
            create_at TEXT DEFAULT CURRENT_TIMESTAMP
            )""")
            self.__conn__.commit()
            log.info('表：notes 创建成功')
        except sqlite3.OperationalError as e:
            if 'already exists' in str(e):
                log.info('表：notes 已存在, 跳过创建')
            else:
                log.error('表：notes 创建失败')
                raise e
    
    def insert_note(self, teacher, note):
        self.__cursor__.execute("INSERT INTO notes (teacher, note) VALUES (?, ?)", (teacher, note))
        self.__conn__.commit()

    def get_notes(self, month = 0):
        if month == 0:
            # Get current month's records
            self.__cursor__.execute("SELECT * FROM notes WHERE strftime('%m', create_at) = strftime('%m', 'now')")
        else:
            # Get specified month's records
            self.__cursor__.execute("SELECT * FROM notes WHERE strftime('%m', create_at) = ?", (str(month).zfill(2),))
        return self.__cursor__.fetchall()
    
async def insert_note(record: any):
    """
    触发条件 记录=(.*)
    添加课时记录碎片
    """
    # text = "记录=迟京超@请半天假（无课时）"
    text = record.content
    pattern = r"^记录=(.*)"
    match = re.search(pattern, text)

    if match:
        content = match.group(1)
        if '@' in content:
            teacher = content.split('@')[0]
            note = content.split('@')[1]
        else:
            teacher = ''
            note = content
        n = Notes()
        n.__enter__()
        n.insert_note(teacher, note)
        send_remind(f'记录已添加：{teacher} {note}', record.roomid)

async def get_notes(record: any):
    """
    触发条件 ^课时记录查询@9
    查询课时记录碎片
    """
    n = Notes()
    n.__enter__()
    if '@' in record.content:
        month = record.content.split('@')[1]
        notes = n.get_notes(month)
    else:
        notes = n.get_notes()
        month = '本'
    res = f'{month}月共有记录{len(notes)}条:\n\n'
    for note in notes:
        res = res + f"{note[0]}. {note[3]} {note[1]} {note[2]} \n"
    # # LOG.info(res)
    send_remind(res, record.roomid)

