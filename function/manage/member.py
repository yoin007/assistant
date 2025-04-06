# _*_ coding :utf-8 _*_
# @Time : 2024/09/28 18:20
# @Author : Tech_T

import re
import requests
import sqlite3
import time
import uuid

from config.config import Config
from config.log import LogConfig
from sendqueue import QueueDB

config = Config()
log = LogConfig().get_logger()

def send_remind(tips, receiver, produce='manage'):
    mid = str(time.time().__int__()) + str(uuid.uuid4())
    with QueueDB() as q:
        q.send_text(mid, tips, receiver, '', produce)
    time.sleep(1)

class Member:
    def __enter__(self, db='databases/member.db'):
        self.__conn__ = sqlite3.connect(db)
        self.__cursor__ = self.__conn__.cursor()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.__conn__.close()
    # -----------------------------create table---------------------------------
    def __create_table__(self):
        try:
            self.__cursor__.execute("""
            CREATE TABLE member(
                uuid TEXT PRIMARY KEY,
                wxid TEXT,
                alias TEXT,
                score INTEGER DEFAULT 50,
                balance INTEGER DEFAULT 0,
                level INTEGER DEFAULT 5,
                module TEXT,
                birthday TEXT,
                activate BOOLEAN DEFAULT 1,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                note TEXT)""")
            self.__conn__.commit()
            log.info('表：member 创建成功')
        except sqlite3.OperationalError as e:
            if 'already exists' in str(e):
                log.info('表：member 已存在, 跳过创建')
            else:
                log.error('表：member 创建失败')
                raise e

        try:
            self.__cursor__.execute("""
            CREATE TABLE contacts(
                wxid TEXT PRIMARY KEY,
                remark TEXT,
                name TEXT,
                gender INTEGER,
                city TEXT,
                province TEXT,
                country TEXT,
                code TEXT)""")
            self.__conn__.commit()
            log.info('表：contacts 创建成功')
        except sqlite3.OperationalError as e:
            if 'already exists' in str(e):
                log.info('表：contacts 已存在, 跳过创建')
            else:
                log.error('表：contacts 创建失败')
                raise e
            
        try:
            self.__cursor__.execute("""
            CREATE TABLE score_record(
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                uuid TEXT,
                source_id TEXT,
                event TEXT,
                type TEXT,
                score INTEGER,
                left_score INTEGER,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP)""")
            self.__conn__.commit()
            log.info('表：score_history 创建成功')
        except sqlite3.OperationalError as e:
            if 'already exists' in str(e):
                log.info('表：score_history 已存在, 跳过创建')
            else:
                log.error('表：score_history 创建失败')
                raise e
            
        try:
            self.__cursor__.execute("""
            CREATE TABLE score_type(
                event TEXT PRIMARY KEY,
                type TEXT,
                score INTEGER,
                money float,
                note TEXT)""")
            self.__conn__.commit()
            log.info('表：score_type 创建成功')
        except sqlite3.OperationalError as e:
            if 'already exists' in str(e):
                log.info('表：score_type 已存在, 跳过创建')
            else:
                log.error('表：score_type 创建失败')
                raise e
    
        try:
            self.__cursor__.execute("""
            CREATE TABLE permission(
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                func_name TEXT,
                func TEXT,
                active BOOLEAN DEFAULT 1,
                black_list TEXT,
                white_list TEXT,
                type TEXT,
                pattern TEXT,
                need_at BOOLEAN DEFAULT 0,
                reply TEXT,
                module TEXT,
                level TEXT,
                example TEXT,
                score_event TEXT)""")
            self.__conn__.commit()
            log.info('表：permission 创建成功')
        except sqlite3.OperationalError as e:
            if 'already exists' in str(e):
                log.info('表：permission 已存在, 跳过创建')
            else:
                log.error('表：permission 创建失败')
                raise e
    
    @staticmethod
    def wx_contacts():
        q = QueueDB()
        q.token = q.get_token(Config().get_config('wcf_admin'), Config().get_config('wcf_pwd'))  # Refresh token
        headers = {
            'accept': 'application/json',
            'Content-Type': 'application/json',
            'Authorization': f'Bearer {q.token}'
        }
        wcf_http_url = Config().get_config('wcf_http_url')
        try:
            response = requests.get(wcf_http_url + 'get_contacts', headers=headers)
            response.raise_for_status()  # Raise an exception for bad status codes
            return response.json()
        except requests.exceptions.RequestException as e:
            log.error(f"获取联系人列表失败：{str(e)}")
            if hasattr(e.response, 'json'):
                error_detail = e.response.json().get('detail', '')
                if 'Not authenticated' in error_detail:
                    log.error("认证失败，请检查token是否有效")
                    # Try to refresh token and retry once
                    try:
                        q.token = q.get_token(Config().get_config('wcf_admin'), Config().get_config('wcf_pwd'))  # Refresh token
                        headers['Authorization'] = f'Bearer {q.token}'
                        response = requests.get(wcf_http_url + 'get_contacts', headers=headers)
                        response.raise_for_status()
                        return response.json()
                    except Exception as retry_e:
                        log.error(f"刷新token后重试失败：{str(retry_e)}")
            return []
    # -------------------------table: contacts---------------------------------
    # 获取所有微信联系人
    def update_contacts(self):
        members = self.__cursor__.execute("SELECT wxid FROM contacts").fetchall()
        members = [member[0] for member in members]
        # print(members)
        contacts = self.wx_contacts()
        # print(contacts)
        if not isinstance(contacts, list):
            log.error("获取联系人列表失败：返回数据格式错误")
            return
            
        for contact in contacts:
            if not isinstance(contact, dict):
                log.error(f"联系人数据格式错误：{contact}")
                continue
                
            try:
                if contact.get('wxid') not in members:
                    self.__cursor__.execute("INSERT INTO contacts (wxid, remark, name, gender, city, province, country, code) VALUES (?, ?, ?, ?, ?, ?, ?, ?)", 
                        (contact.get('wxid'), contact.get('remark'), contact.get('name'), contact.get('gender'), 
                         contact.get('city'), contact.get('province'), contact.get('country'), contact.get('code')))
                    # print(f"{contact.get('wxid')} 插入成功")
                else:
                    self.__cursor__.execute("UPDATE contacts SET remark = ?, name = ?, gender = ?, city = ?, province = ?, country = ?, code = ? WHERE wxid = ?", 
                        (contact.get('remark'), contact.get('name'), contact.get('gender'), contact.get('city'), 
                         contact.get('province'), contact.get('country'), contact.get('code'), contact.get('wxid')))
                    # print(f"{contact.get('wxid')} 更新成功")
            except Exception as e:
                log.error(f"处理联系人数据失败：{str(e)}")
                continue
                
        self.__conn__.commit()
        self.__conn__.close()
        log.info('联系人更新成功')
    
    def wxid_name(self, wxid):
        """
        从 contacts 表中获取 wxid 对应的 name
        :param wxid: 微信id
        :return: name
        """
        self.__cursor__.execute("SELECT name, remark FROM contacts WHERE wxid = ?", (wxid,))
        result = self.__cursor__.fetchone()
        return result if result else None

    
    # -------------------------table: member---------------------------------
    def insert_member(self, uuid, wxid, alias, level, model, note=''):
        """
        往数据库添加会员信息
        :param uuid: 会员uuid
        :param wxid: 会员wxid
        :param alias: 会员别名
        :param note: 备注
        """
        self.__cursor__.execute("INSERT INTO member (uuid, wxid, alias, level, module, birthday, note) VALUES (?, ?, ?, ?, ?,'', ?)", (uuid, wxid, alias, level, model, note))
        self.__conn__.commit()
    
    def delte_member(self, uuid):
        """
        删除会员信息
        :param uuid: 会员uuid
        """
        self.__cursor__.execute("DELETE FROM member WHERE uuid =?", (uuid,))
        self.__conn__.commit()
    
    def member_info(self, uuid):
        """
        查询会员信息
        :param uuid: 会员uuid
        :return: 会员信息
        """
        self.__cursor__.execute("SELECT * FROM member WHERE uuid = ?", (uuid,))
        result = self.__cursor__.fetchone()
        result = result if result else None
        return result

    # -------------------------table: score---------------------------------
    def event_score(self, uuid, event, left_score):
        """
        1. 根据 event 查询对应的积分变化
        2. 计算积分变化
        3. 添加记录到 score_record 表中
        4. 调用 update_score 更新会员积分
        :param uuid: 会员uuid
        :param event: 事件
        :param left_score: 剩余积分
        """
        pass

    # -------------------------table: permission---------------------------------
    def permission_info(self, func_name=''):
        """
        查询权限信息
        :param func_name: 函数名
        :return: 权限信息
        """
        if func_name == '':
            self.__cursor__.execute("SELECT * FROM permission")
            result = self.__cursor__.fetchall()
            return result if result else None
        else:
            self.__cursor__.execute("SELECT * FROM permission WHERE func_name = ?", (func_name,))
            result = self.__cursor__.fetchone()
            return result if result else None
    
    def permission_info_by_id(self, id):
        """ 通过 id 查询权限信息 """
        self.__cursor__.execute("SELECT * FROM permission WHERE id =?", (id,))
        result = self.__cursor__.fetchone()
        return result if result else None
    
    def add_permission(self, func_name, func, active, black_list, white_list, type, pattern, need_at, reply, module, level, example, score_event):
        """
        添加权限信息
        """
        try:
            cursor = self.__cursor__.execute("INSERT INTO permission (func_name, func, active, black_list, white_list, type, pattern, need_at, reply, module, level, example, score_event) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
                                (func_name, func, active, black_list, white_list, type, pattern, need_at, reply, module, level, example, score_event))
            self.__conn__.commit()
            if cursor.rowcount > 0:
                log.info(f'添加权限：{func_name} 成功')
                return True
            else:
                log.warning(f'添加权限：{func_name} 失败，未插入任何行')
                return False
        except sqlite3.Error as e:
            log.error(f'添加权限：{func_name} 失败，错误：{str(e)}')
            return False
    
    def inactive_func(self, func_name):
        """
        停用函数
        :param func_name: 函数名
        """
        c = self.__cursor__.execute("UPDATE permission SET active = 0 WHERE func_name = ?", (func_name,))
        if c.rowcount == 0:
            log.error(f'停用函数失败：{func_name}')
        else:
            self.__conn__.commit()
            log.info(f'停用函数：{func_name}')
    
    def active_func(self, func_name):
        """
        启用函数
        :param func_name: 函数名
        """
        self.__cursor__.execute("UPDATE permission SET active = 1 WHERE func_name = ?", (func_name,))
        self.__conn__.commit()
        log.info(f'启用函数：{func_name}')

async def query_permission(record):
    """
    查询权限信息
    :param record: 消息记录
    :return: 权限信息
    """
    text = record.content
    pid = re.match(r"^权限查询-(\d+)$", text)
    if not pid:
        send_remind('权限查询失败：请输入正确的权限id', record.sender)
        return None
    pid = pid.group(1)
    with Member() as m:
        permission = m.permission_info_by_id(pid)
        if not permission:
            send_remind('权限查询失败：权限id不存在', record.sender)
            return None
        else:
            tips = f'id：{permission[0]}\n' \
                    f'函数名：{permission[1]}\n' \
                    f'函数：{permission[2]}\n' \
                    f'是否启用：{permission[3]}\n' \
                    f'黑名单：{permission[4]}\n' \
                    f'白名单：{permission[5]}\n' \
                    f'类型：{permission[6]}\n' \
                    f'正则表达式：{permission[7]}\n' \
                    f'是否需要at：{permission[8]}\n' \
                    f'回复：{permission[9]}\n' \
                    f'模块：{permission[10]}\n' \
                    f'最低等级：{permission[11]}\n' \
                    f'示例：{permission[12]}\n' \
                    f'积分事件：{permission[13]}'
            send_remind(tips, record.sender)
            return None

async def insert_permission(record):
    """
    添加权限信息
    :param record: 消息记录
    :return: 权限信息
    """
    print(record.content)
    # 解析权限信息
    try:
        lines = record.content.strip().split('\n')
        # 提取各字段信息
        func_name = lines[1].split('：')[1].strip() if len(lines) > 1 else ''
        func = lines[2].split('：')[1].strip() if len(lines) > 2 else ''
        active = int(lines[3].split('：')[1].strip()) if len(lines) > 3 else 1
        black_list = lines[4].split('：')[1].strip() if len(lines) > 4 else ''
        white_list = lines[5].split('：')[1].strip() if len(lines) > 5 else ''
        type_value = lines[6].split('：')[1].strip() if len(lines) > 6 else ''
        pattern = lines[7].split('：')[1].strip() if len(lines) > 7 else ''
        need_at = int(lines[8].split('：')[1].strip()) if len(lines) > 8 else 0
        reply = lines[9].split('：')[1].strip() if len(lines) > 9 else ''
        module = lines[10].split('：')[1].strip() if len(lines) > 10 else ''
        level = lines[11].split('：')[1].strip() if len(lines) > 11 else '5'
        example = lines[12].split('：')[1].strip() if len(lines) > 12 else ''
        score_event = lines[13].split('：')[1].strip() if len(lines) > 13 else ''
        
        # 处理None值
        black_list = None if black_list == 'None' else black_list
        white_list = None if white_list == 'None' else white_list
        reply = None if reply == 'None' else reply
        score_event = None if score_event == 'None' else score_event
        
        # 验证必填字段
        if not active or not pattern or not module or not white_list or not level:
            send_remind('添加权限失败：缺少必要字段（是否启用、正则表达式、模块、白名单、最低等级）', record.sender)
            return False
        # 添加权限
        with Member() as m:
            success = m.add_permission(
                func_name, func, active, black_list, white_list, 
                type_value, pattern, need_at, reply, module, 
                level, example, score_event
            )
            
            if success:
                send_remind(f'添加权限成功：{func_name}', record.sender)
            else:
                send_remind(f'添加权限失败：数据库操作错误', record.sender)
                
    except Exception as e:
        log.error(f'添加权限出错：{record.id} - {record.content} - {e}')
        send_remind(f'添加权限失败：{str(e)}', record.sender)
    return None

def wxid_name_remark(wxid):
    """
    从 contacts 表中获取 wxid 对应的 name
    :param wxid: 微信id
    """
    with Member() as m:
        result = m.wxid_name(wxid)
        if not result:
            m.update_contacts()
            with Member() as m2:  # Create a new connection for the second query
                result = m2.wxid_name(wxid)
                if not result:
                    return None
                # else:
                #     print(result)
        return result


async def insert_member(record):
    """
    插入会员信息
    :param record: 会员信息
    支持添加会员时，指定level和model
    示例：添加会员: abc-10-lesson
    """
    level = 5
    model = 'basic'
    results = record.content.split('-')
    if len(results) == 3:
        level = results[1]
        model += f"/{results[2]}"
    if '@chatroom' in record.roomid:
        text = record.content.split('-')[0]
        pattern = r'@(\w+)'
        matches = re.findall(pattern, text)
        at_list = record.parsexml.replace('"', '').split(',')
        print(matches, at_list)
        with Member() as m:
            if len(at_list) == len(matches):
                for k, v in zip(at_list, matches):
                    uuid = k + '#' + record.roomid
                    row = m.member_info(uuid)
                    if row:
                        send_remind(f'会员已存在：{uuid}', record.sender)
                    else:
                        m.insert_member(uuid, k, v, level, model)
                        send_remind(f'添加会员：{uuid}, {k}, {v}', record.sender)

            else:
                send_remind(f'添加会员出错1：{record.id} - {record.content}', record.sender)
    else:
        try:
            member_str = record.content.replace('：', ':').replace(' ', '').split('-')[0].split(':')[1]
            member_list = member_str.split(',') 
            for member in member_list:
                with Member() as m:
                    row = m.member_info(member)
                if row:
                    send_remind(f'会员已存在：{member}', record.sender)
                else:
                    name = ''
                    alias = wxid_name_remark(member)
                    if alias:
                        name = alias[1] if alias[1] else alias[0]
                    if name:
                        with Member() as m4:
                            m4.insert_member(member, member, name, level, model)
                            send_remind(f'添加会员：{member}, {member}, {name}', record.sender)
                    else:
                        send_remind(f'添加会员出错2：{record.id} - 无该好友：{record.content}', record.sender)
        except Exception as e:
            send_remind(f'添加会员出错3：{record.id} - {record.content} - {e}', record.sender)

async def del_member(record):
    """
    删除会员信息
    :param record: 消息记录
    """
    member_str = record.content.replace('删除会员', '').replace('：', ':').replace(' ', '').split(':')[1]
    member_list = member_str.split(',')
    for member in member_list:
        with Member() as m:
            m.delte_member(member)
            send_remind(f'删除会员：{member}', record.sender)
    return None
                        
def check_permission(func):
    async def wrapper(record, *args, **kwargs):
        if has_permission(func, record, *args, **kwargs):
            return await func(record, *args, **kwargs)
        else:
            log.warning(f"{record.id} - {func.__name__}：鉴权失败")
    return wrapper
        
def has_permission(func, record, *args, **kwargs):
    """
    鉴权
    :param func: 被装饰的函数
    :param record: 消息记录
    """
    if record.is_group:
        uuid = record.sender + '#' + record.roomid
    else:
        uuid = record.sender
    func_name = func.__name__
    with Member() as m:
        permission = m.permission_info(func_name)
        member_info = m.member_info(uuid)
        if member_info:
            if permission:
                print(permission)
                if permission[10] in member_info[6].split('/'):
                    if int(member_info[5]) >= int(permission[11]):
                        log.info(f"{record.id} - {func_name}：权限通过")
                        return True
                    else:
                        log.warning(f"{record.id} - {func_name}：{uuid}-会员等级不足")
                else:
                    log.warning(f"{uuid}-尚未开通 {permission[10]} 模块权限")
            else:
                log.warning(f"{func_name} 尚未开启权限检测，请检查配置")
        else:
            log.warning(f"{uuid} 尚未开通会员")
    return False

async def start_func(record: any):
    if record.sender not in config.get_config('admin_list'):
        return False
    pattern = r"^START (.*)"
    match = re.search(pattern, record.content)
    if match:
        func_name = match.group(1)
        try:
            with Member() as m:
                m.active_func(func_name)
                send_remind(f"start_func: {func_name}", record.sender)
                return True
        except Exception as e:
            log.error(f"start_func Failed: {e}")
            return False
    
async def stop_func(record: any):
    if record.sender not in config.get_config('admin_list'):
        return False
    pattern = r"^STOP (.*)"
    match = re.search(pattern, record.content)
    if match:
        func_name = match.group(1)
        try:
            with Member() as m:
                m.inactive_func(func_name)
                send_remind(f"stop_func: {func_name}", record.sender)
                return True
        except Exception as e:
            log.error(f"stop_func Failed: {e}")
            return False