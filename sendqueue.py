# _*_ coding: utf-8 _*_
# @Time: 2024/09/23 18:27
# @Author: Tech_T


import json
import requests
import sqlite3
import time
from datetime import datetime, timedelta
import threading

from config.log import LogConfig
from config.config import Config

log = LogConfig().get_logger()
config = Config()
wcf = config.get_config('wcf_http_url')
user = config.get_config('wcf_admin')
pwd = config.get_config('wcf_pwd')


class QueueDB:
    _instance = None
    _lock = threading.Lock()

    def __new__(cls, *args, **kwargs):
        if not cls._instance:
            with cls._lock:
                if not cls._instance:
                    cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self):
        if hasattr(self, 'initialized'):
            return
        self.initialized = True
        self.expeired_minutes = 28
        self.expeired_time = None
        self.token = self.get_token(user, pwd)
        self._local = threading.local()

    def __enter__(self, db='databases/queues.db'):
        if not hasattr(self._local, 'connection'):
            self._local.connection = sqlite3.connect(db)
            self._local.cursor = self._local.connection.cursor()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        if hasattr(self._local, 'connection'):
            self._local.connection.close()
            del self._local.connection
            del self._local.cursor

    def __create_table__(self):
        """
        创建队列表
        producer: 消息生产者
        consumer: 消息消费者
        p_time: 消息生产时间
        c_time: 消息消费时间
        """
        self._local.cursor.execute('''
            CREATE TABLE IF NOT EXISTS queues (
                id TEXT,
                is_consumed BOOLEAN DEFAULT 0,
                data TEXT,
                producer TEXT,
                p_time TEXT,
                consumer TEXT,
                c_time TEXT,
                timestamp INTEGER                          
                )''')
        self._local.connection.commit()

    def __produce__(self, m_id: str, data: dict, consumer: str, producer: str):
        """
        生产消息队列
        :param m_id: 消息id
        :param data: 消息内容
        :param producer: 消息生产者
        :param consumer: 消息消费者,api的完整地址 eg: http://127.0.0.1:9999/text
        :return:
        """
        data_string = json.dumps(data, ensure_ascii=False)

        record = {
            'id': m_id,
            'data': data_string,
            'producer': producer,
            'p_time': time.strftime("%Y-%m-%d %H:%M:%S", time.localtime()),
            'consumer': consumer,
            'c_time': '',
            'timestamp': time.time().__int__()
        }
        try:
            self._local.cursor.execute('''
            INSERT INTO queues (id, data, producer, p_time, consumer, c_time, timestamp) VALUES (:id, :data, :producer, :p_time, :consumer, :c_time, :timestamp)
            ''', record)
            self._local.connection.commit()
        except Exception as e:
            log.error(f'生产消息队列失败: {e}')

    def get_token(self, username: str, password: str):
        now = datetime.now()
        if self.expeired_time and now < self.expeired_time:
            return self.token
        self.expeired_time = now + timedelta(minutes=self.expeired_minutes)
        try:
            response = requests.post(
                f'{wcf}token',
                headers={
                    'accept': 'application/json',
                    'Content-Type': 'application/x-www-form-urlencoded'
                },
                data={'username': username, 'password': password}
            )
            response.raise_for_status()  # 如果响应状态码不是200，将抛出HTTPError异常
            token_data = response.json()
            print(token_data)
            return token_data.get('access_token')
        except requests.exceptions.RequestException as e:
            log.error(f"请求失败：{e}")
            return None

    def __consume__(self):
        """
        消费消息队列
        :return:
        """
        # 检查token是否过期
        now = datetime.now()
        if now >= self.expeired_time:
            _token = self.get_token(user, pwd)
            self.token = _token
        else:
            _token = self.token

        # 创建新的数据库连接
        with sqlite3.connect('databases/queues.db') as conn:
            cursor = conn.cursor()
            try:
                cursor.execute('''
                SELECT * FROM queues WHERE is_consumed = 0 ORDER BY timestamp ASC LIMIT 1
                ''')
                record = cursor.fetchone()
                if record:
                    headers = {
                        'accept': 'application/json',
                        'Authorization': f'Bearer {_token}'
                    }
                    r = requests.post(
                        url=record[5],
                        json=json.loads(record[2]),
                        headers=headers
                    )
                    print(r.status_code)
                    c_time = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime())
                    cursor.execute('''
                    UPDATE queues SET is_consumed = 1, c_time = ? WHERE id = ?
                    ''', (c_time, record[0]))
                    conn.commit()
                    return record
            except Exception as e:
                log.error(f'消费消息队列失败: {e}-{record[5] if record else ""}')
                return None

    # V39.2.4版本@消息有@效果，V39.4.4版本@消息无@效果
    def send_text(self, m_id: str, msg: str, receiver: str, aters: str = '', producer: str = 'main'):
        data = {
            'msg': msg,
            'receiver': receiver,
            'aters': aters
        }
        self.__produce__(m_id, data, wcf + 'text', producer)

    def send_image(self, m_id: str, img_path: str, receiver: str, producer: str = 'main'):
        data = {
            'path': img_path,
            'receiver': receiver,
        }
        self.__produce__(m_id, data, wcf + 'image', producer)

    def send_file(self, m_id: str, file_path: str, receiver: str, producer: str = 'main'):
        data = {
            'path': file_path,
            'receiver': receiver,
        }
        self.__produce__(m_id, data, wcf + 'file', producer)

    def send_rich_text(self, m_id: str, name: str, account: str, title: str, digest: str, url: str, thumbnail: str, receiver: str, producer: str = 'main'):
        data = {
            'name': name,
            'account': account,
            'title': title,
            'digest': digest,
            'url': url,
            'thumbnail': thumbnail,
            'receiver': receiver,
        }
        self.__produce__(m_id, data, wcf + 'rich-text', producer)

    # V39.4.4版本邀请入群调用了方法但未生效,V39.2.4版本可用
    def cr_members(self, m_id: str, chatroom: str, wxids: str, producer: str = 'main'):
        data = {
            'roomid': chatroom,
            'wxids': wxids,
        }
        self.__produce__(m_id, data, wcf + 'invite-chatroom-member', producer)

    def accept_new_friend(self, mid: str, scence: int, v3: str, v4: str, producer: str = 'main'):
        data = {
            'scence': scence,
            'v3': v3,
            'v4': v4,
        }
        self.__produce__(mid, data, wcf + 'accept-new-friend', producer)

    def save_file(self, m_id: str, id: int, extra: str, dst: str, producer: str = 'main'):
        data = {
            'id': id,
            'extra': extra,
            'dst': dst,
        }
        self.__produce__(m_id, data, wcf + 'save-file', producer)
    
    def alias(self, wxid, roomid):
        # 检查token是否过期
        now = datetime.now()
        if now >= self.expeired_time:
            _token = self.get_token(user, pwd)
            self.token = _token
        else:
            _token = self.token
        headers = {
            'accept': 'application/json',
            'Authorization': f'Bearer {_token}'
        }
        data = {
            "roomid": roomid,
            "wxid": wxid
        }
        r = requests.post(wcf + 'alias', json=data, headers=headers)
        if r.status_code == 200:
            return r.json()
        else:
            return ''


if __name__ == '__main__':
    db = QueueDB()
    db.__enter__()
    db.__create_table__()
    print('Done!')
