# _*_ coding: utf-8 _*_
# @Time : 2024/10/7 20:56
# @Author : Tech_T

from calendar import c
import json
import os
import re
import shutil
import time
import uuid
from datetime import datetime, timedelta
from html2image import Html2Image

import pandas as pd
import requests
from config.config import Config
from config.log import LogConfig
from sendqueue import QueueDB
from function.manage.member import check_permission

log = LogConfig().get_logger()


def send_remind(tips, receiver, produce='lesson'):
    mid = str(time.time().__int__()) + str(uuid.uuid4())
    with QueueDB() as q:
        q.send_text(mid, tips, receiver, '', produce)
    time.sleep(1)


def send_image(image_path, receiver, produce='lesson'):
    mid = str(time.time().__int__()) + str(uuid.uuid4())
    with QueueDB() as q:
        q.send_image(mid, image_path, receiver, produce)
    time.sleep(1)


def send_file(file_path, receiver, produce='lesson'):
    mid = str(time.time().__int__()) + str(uuid.uuid4())
    with QueueDB() as q:
        q.send_file(mid, file_path, receiver, produce)
    time.sleep(1)


class Lesson:
    _instance = None  # Singleton instance

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    # ---------- 初始化信息 ----------
    def __init__(self):
        if hasattr(self, '_initialized'):
            return
        self.datashow_info = Config().get_config('datashow_info')
        self.lesson_dir = Config().get_config('lesson_dir')
        self.admin = Config().get_config('lesson_admin')
        self.create_c_month_dir()
        self.week_change = -5
        # 类级别的缓存
        self._cache_ttl = 3600  # 缓存有效期（秒）
        # 错误消息常量
        self.ERROR_MESSAGES = {
            'DATE_NOT_FOUND': "课表中未找到'date'列",
            'DATE_INVALID': "课表日期无效: {}",
            'MISSING_COLUMNS': "课表缺少必需列: {}",
            'REPEATED_SUBJECTS': "课表中存在重复科目:\n{}",
            'SCHEDULE_CHECK_FAILED': "课表检查失败: {}"
        }
        self.refresh_cache()
        self._initialized = True

    def refresh_cache(self):
        """刷新所有缓存"""
        self._last_cache_update = time.time()
        # 清除所有缓存
        self._teacher_template_cache = None
        self._current_schedule_file = None
        self._class_template_cache = None
        self._ip_info_cache = None
        self._contacts_cache = None
        self._time_table_cache = None
        # 重新加载所有缓存
        try:
            self.current_month = self.month_info()
            self.week_info = self.get_week_info()
            self.week_next = self.get_week_next()
            self._class_template_cache = self._load_class_template()
            self._current_schedule_file = self.current_schedule_file(
                week_next=False)
            self._time_table_cache = self._load_time_table()
            self._contacts_cache = self._load_contacts()
            self._ip_info_cache = self._load_ip_info()
            self._teacher_template_cache = self._load_teacher_template()
            log.info("缓存已刷新")
        except Exception as e:
            log.error(f"刷新缓存时发生错误: {str(e)}")
            raise

    def _should_refresh_cache(self):
        """检查是否需要刷新缓存"""
        if not self._last_cache_update:
            return True
        return (time.time() - self._last_cache_update) > self._cache_ttl

    def _load_teacher_template(self):
        """加载教师模板数据"""
        template_path = os.path.join(self.lesson_dir, 'checkTemplate.xlsx')
        if not os.path.exists(template_path):
            log.error(f"课程模板文件不存在: {template_path}")
            return pd.DataFrame()

        try:
            return pd.read_excel(
                template_path,
                sheet_name='teachers',
                engine='openpyxl'
            )
        except Exception as e:
            log.error(f"读取课程模板文件失败: {str(e)}")
            return pd.DataFrame()

    def _load_class_template(self):
        """加载班级模板数据"""
        template_path = os.path.join(self.lesson_dir, 'checkTemplate.xlsx')
        if not os.path.exists(template_path):
            log.error(f"课程模板文件不存在: {template_path}")
            return pd.DataFrame()

        try:
            return pd.read_excel(
                template_path,
                sheet_name='class',
                engine='openpyxl'
            )
        except Exception as e:
            log.error(f"读取课程模板文件失败: {str(e)}")
            return pd.DataFrame()

    def _load_time_table(self):
        """加载时间表数据"""
        template_path = os.path.join(self.lesson_dir, 'checkTemplate.xlsx')
        if not os.path.exists(template_path):
            log.error(f"时间表文件不存在: {template_path}")
            return pd.DataFrame()

        try:
            return pd.read_excel(
                template_path,
                sheet_name='class_time',
                engine='openpyxl'
            )
        except Exception as e:
            log.error(f"读取时间表文件失败: {str(e)}")
            return pd.DataFrame()

    def _load_ip_info(self):
        """加载IP信息数据"""
        ip_info_path = os.path.join(self.lesson_dir, 'zhanghao.xlsx')
        if not os.path.exists(ip_info_path):
            log.error(f"账号信息文件不存在: {ip_info_path}")
            return pd.DataFrame()

        try:
            return pd.read_excel(
                ip_info_path,
                index_col='Name',
                engine='openpyxl'
            )
        except Exception as e:
            log.error(f"读取账号信息文件失败: {str(e)}")
            return pd.DataFrame()

    def _load_contacts(self):
        # TODO: 优化
        # 次处的联系人为lesson模块的相关用户，当前方法时通过微信联系人的remark来区分
        # 后续可以考虑在当前的基础上，与checkTemplate中的teachers进行合并比较，确保用户的准确性，避免因人员离职，备注问题导致的错误
        """加载联系人信息数据"""
        try:
            contacts = {}
            q = QueueDB()
            q.token = q.get_token(Config().get_config('wcf_admin'), Config().get_config('wcf_pwd'))
            headers = {
                'accept': 'application/json',
                'Authorization': f'Bearer {q.token}'
            }
            contacts_list = requests.get(Config().get_config(
                'wcf_http_url')+'get_contacts', headers=headers).json()
            contacts.update({
                contact['remark'].replace('天龙', ''): contact['wxid']
                for contact in contacts_list
                if '天龙' in contact['remark']
            })
            return contacts
            # return {'田百航': 'Tech_T','李园路': 'royal1011','袁玲': 'daaiqiuqiu'}
        except Exception as e:
            log.error(f"获取联系人信息失败: {str(e)}")
            return {}

    @property
    def teacher_template(self):
        if self._should_refresh_cache():
            self.refresh_cache()
        return self._teacher_template_cache

    @property
    def class_template(self):
        if self._should_refresh_cache():
            self.refresh_cache()
        return self._class_template_cache

    @property
    def time_table(self):
        if self._should_refresh_cache():
            self.refresh_cache()
        return self._time_table_cache

    @property
    def ip_info(self):
        if self._should_refresh_cache():
            self.refresh_cache()
        return self._ip_info_cache

    @property
    def contacts(self):
        if self._should_refresh_cache():
            self.refresh_cache()
        return self._contacts_cache

    def get_wxids(self, teacher_name) -> list:
        """获取老师或班级的微信ID，如果参数是班级名，则返回班级的班主任的微信ID"""
        wxids = []
        if self.class_template is None or self.contacts is None:
            return wxids
        try:
            if teacher_name in self.class_template['class_name'].tolist():
                class_leaders = dict(
                    zip(self.class_template['class_name'], self.class_template['leaders']))
                leaders = class_leaders[teacher_name].split('/')
                for leader in leaders:
                    wxids.append(self.contacts[leader])
            else:
                wxids.append(self.contacts[teacher_name])
        except KeyError as e:
            log.error(f"KeyError: {str(e)}")
        except IndexError as e:
            log.error(f"IndexError: {str(e)}")
        return wxids

    def notify_admins(self, message: str) -> None:
        """向管理员发送通知"""
        for admin in self.admin:
            send_remind(message, admin)

    @staticmethod
    def month_info() -> str:
        """返回当前月份：202412"""
        # 获取当前日期
        current_date = datetime.now()
        # 获取当前月份
        current_month = current_date.strftime("%Y%m")
        return current_month

    def get_week_info(self) -> list:
        """
        获取当前周的周信息[16, '20241216', 1734278400, 1734883199]
        """
        # 获取当前日期
        current_date = datetime.now()
        current_date = current_date.replace(
            hour=0, minute=0, second=0, microsecond=0)
        # 获取当前周数
        current_week_number = current_date.isocalendar()[1] + self.week_change
        # 获取当前周的周一日期
        monday_date = current_date - timedelta(days=current_date.weekday())
        monday = monday_date.strftime('%Y%m%d')
        monday_timestamp = int(monday_date.timestamp())
        sunday_timestamp = int(
            (monday_date + timedelta(days=7)).timestamp()) - 1
        return [current_week_number, monday, monday_timestamp, sunday_timestamp]

    def get_week_next(self) -> list:
        """
        获取下周的周信息[16, '20241216', 1734278400, 1734883199]
        """
        current_date = datetime.now()
        current_date = current_date.replace(
            hour=0, minute=0, second=0, microsecond=0)
        next_week_number = current_date.isocalendar()[1] + self.week_change + 1
        next_monday_date = current_date + \
            timedelta(days=7) - timedelta(days=current_date.weekday())
        next_monday = next_monday_date.strftime('%Y%m%d')
        next_monday_timestamp = int(next_monday_date.timestamp())
        next_sunday_timestamp = int(
            (next_monday_date + timedelta(days=7)).timestamp()) - 1
        return [next_week_number, next_monday, next_monday_timestamp, next_sunday_timestamp]

    # ---------- 文件（夹）操作 ----------
    def create_c_month_dir(self):
        """
        创建当前月份的文件夹，如果不存在则创建，返回月份目录路径
        """
        now_t = datetime.now()
        c_month = now_t.strftime('%Y%m')
        c_month_dir = os.path.join(self.lesson_dir, c_month)
        
        if not os.path.isdir(c_month_dir):
            try:
                os.mkdir(c_month_dir)
                os.mkdir(os.path.join(c_month_dir, 'class_schedule'))
                os.mkdir(os.path.join(c_month_dir, 'schedule_history'))
                self.notify_admins(f'创建{c_month_dir}文件夹成功')
            except Exception as e:
                self.notify_admins(f'创建{c_month_dir}文件夹失败：{e}')
                log.error(f'创建文件夹失败：{e}')
                return ''
        
        return c_month_dir  # 无论目录是否存在，都返回目录路径

    def _handle_file_error(self, operation: str, error_msg: str, source: str = '', dest: str = ''):
        """统一处理文件操作错误, 通知管理员"""
        error = f"无法{operation}"
        if source:
            error += f" {source}"
        if dest:
            error += f" 到 {dest}"
        error += f": {error_msg}"

        log.error(error)
        self.notify_admins(error)
        return 0

    def move_folder(self, src='', dst='history') -> int:
        """文件夹迁移，把上月的数据文件迁移至 history 文件夹（暂时未用到）"""
        now_t = datetime.now()
        last_month = now_t - timedelta(days=now_t.day)
        p_month = last_month.strftime("%Y%m")
        src_dir = os.path.join(self.lesson_dir, src) if src else os.path.join(
                self.lesson_dir, p_month)
        dst_dir = os.path.join(self.lesson_dir, dst,
                                   p_month) if dst == 'history' else dst
        try:
            if not os.path.exists(src_dir):
                return self._handle_file_error("移动", "源目录不存在", src_dir)

            os.makedirs(dst_dir, exist_ok=True)
            log.info(f"正在移动文件夹: 从 {src_dir} 到 {dst_dir}")

            for item in os.listdir(src_dir):
                src_path = os.path.join(src_dir, item)
                dst_path = os.path.join(dst_dir, item)

                try:
                    if os.path.isdir(src_path):
                        self.move_folder(src_path, dst_path)
                    else:
                        shutil.move(src_path, dst_path)
                except Exception as e:
                    return self._handle_file_error("移动", str(e), src_path, dst_path)

            if not os.listdir(src_dir):
                shutil.rmtree(src_dir)
                log.info(f"已删除空目录: {src_dir}")

            return 1

        except Exception as e:
            return self._handle_file_error("移动目录", str(e), src_dir, dst_dir)

    def copy_file(self, source_path: str, destination_path: str) -> int:
        """复制文件到指定位置"""
        if not os.path.exists(source_path):
            return self._handle_file_error("复制", "源文件不存在", source_path)

        try:
            os.makedirs(os.path.dirname(destination_path), exist_ok=True)
            shutil.copy2(source_path, destination_path)
            log.info(f"文件复制成功: 从 {source_path} 到 {destination_path}")
            return 1
        except Exception as e:
            return self._handle_file_error("复制文件", str(e), source_path, destination_path)

    def move_file(self, source_path: str, destination_path: str) -> int:
        """移动文件到指定位置"""
        if not os.path.exists(source_path):
            return self._handle_file_error("移动", "源文件不存在", source_path)

        try:
            os.makedirs(os.path.dirname(destination_path), exist_ok=True)
            shutil.move(source_path, destination_path)
            log.info(f"文件移动成功: 从 {source_path} 到 {destination_path}")
            return 1
        except Exception as e:
            return self._handle_file_error("移动文件", str(e), source_path, destination_path)

    # TODO: 生成课表,该方法暂时不启用，因为每周课表变化较大，都需要人工上传
    def generate_weekly_schedule(self) -> int:
        """
            生成当周课表,正确返回1,错误返回0
        """
        tb_init = self.week_info[1] + '-' + str(self.week_info[2])
        dest_path = os.path.join(
            self.lesson_dir, self.current_month, 'class_schedule', '课表' + tb_init + '.xlsx')
        if os.path.exists(dest_path):
            return 0
        try:
            template = pd.read_excel(
                self._current_schedule_file, engine='openpyxl')
            df = template.copy()
            df['date'] = self.week_info[1]
            df['date'] = df.apply(lambda row: (pd.to_datetime(
                row['date']) + pd.Timedelta(days=row['diff'])).strftime('%d'), axis=1)
            df.drop(columns=['diff'], inplace=True)
            df['date'] = df['date'].astype(int)
            last_column = df.columns[-1]
            # 获取最后一列的列名
            last_column = df.columns[-1]
            # 创建新的列顺序，将最后一列放在第二列位置
            new_order = [df.columns[0]] + \
                [last_column] + list(df.columns[1:-1])
            # 重新排列DataFrame的列
            df = df[new_order]
            df.to_excel(dest_path, index=False, engine='openpyxl')
            self.notify_admins(f'本周课表已生成')
            return 1
        except Exception as e:
            log.error(f"无法生成课表. {str(e)}")
            self.notify_admins(f'本周课表生成失败，请检查日志')
            return 0

    def current_schedule_file(self, week_next: bool = False) -> str:
        """
        获取当前(下周)课表文件路径,返回str
        """
        if self._should_refresh_cache():
            self.refresh_cache()

        schedule_dir = os.path.join(
            self.lesson_dir, self.current_month, 'class_schedule')
        if week_next:
            monday = self.week_next[1]
        else:
            monday = self.week_info[1]
        schedule_file_sorted = self.sorted_schedule_file(schedule_dir, monday)
        if len(schedule_file_sorted) == 0:
            return ''
        return os.path.join(schedule_dir, schedule_file_sorted[0])

    def format_schedule(self, df_schedule: pd.DataFrame, week_next: bool = False, ignore: bool = False) -> pd.DataFrame:
        """
        格式化课表, 将课表中的标点符号统一化，并根据单双周进行调整（选择实际上课的科目）

        Args:
            df_schedule: 课表DataFrame
            week_next: 是否是下周课表
            ignore: 是否忽略特定科目

        Returns:
            pd.DataFrame: 格式化后的课表
        """
        # 替换NaN值为'-'
        df_schedule = df_schedule.fillna('-')

        # 读取替换模板
        replace_template = pd.read_excel(
            os.path.join(self.lesson_dir, 'checkTemplate.xlsx'),
            sheet_name='replace',
            engine='openpyxl'
        )
        replace_dict = dict(
            zip(replace_template['string'], replace_template['replace']))
        # 定义字符串处理函数

        def clean_string(x):
            if not isinstance(x, str):
                return x
            # 链式调用string方法
            result = str(x).strip()
            # 使用正则表达式一次性替换所有空白字符
            result = re.sub(r'\s+', '', result)
            # 批量替换标点符号
            for old, new in replace_dict.items():
                if old in result:
                    result = result.replace(old, new)
            return result.strip()

        # 使用apply函数进行数据转换
        df_schedule = df_schedule.map(clean_string)

        # 处理需要忽略的科目
        if ignore:
            ignore_subject = pd.read_excel(
                os.path.join(self.lesson_dir, 'checkTemplate.xlsx'),
                sheet_name='ignore',
                engine='openpyxl'
            )['subject'].tolist()

            def ignore_subjects(x):
                return '-' if x in ignore_subject else x

            df_schedule = df_schedule.map(ignore_subjects)

        # 处理单双周
        def process_week_schedule(x):
            if not isinstance(x, str):
                return x

            current_week = self.week_info[0]
            week_flag = '单' if (not week_next and current_week % 2 == 1) or (
                week_next and current_week % 2 == 0) else '双'

            subjects = x.split('/')
            if len(subjects) == 2:
                # print(subjects)
                for subject in subjects:
                    if f'({week_flag})' in subject:
                        return subject.replace(f'({week_flag})', '').strip()
            return x

        # 使用apply函数处理单双周
        df_schedule = df_schedule.map(process_week_schedule)

        return df_schedule

    def get_subject_teacher(self, subject: str) -> str:
        """获取科目对应的老师"""
        subject_teacher = pd.read_excel(os.path.join(
            self.lesson_dir, 'checkTemplate.xlsx'), sheet_name='teachers', engine='openpyxl').apply(list, axis=1)
        for s_t in subject_teacher:
            if subject in s_t[1].split('/'):
                return s_t[0]
        return subject

    def repalce_subject_teacher(self, df_schedule: pd.DataFrame, teacher_flag: bool = True, week_next: bool = False, ignore: bool = False) -> pd.DataFrame:
        """
        将课表中的科目替换为对应的老师，teacher_flag 默认为 True，如果改为False，则替换科目
        但是发现替换学科可以直接用字符串截取前两个字符更符合实际应用
        """
        df_schedule = self.format_schedule(
            df_schedule, week_next=week_next, ignore=ignore)
        subject_teacher = pd.read_excel(os.path.join(
            self.lesson_dir, 'checkTemplate.xlsx'), sheet_name='teachers', engine='openpyxl').apply(list, axis=1)
        if self.class_template is None:
            return df_schedule
        required_columns = self.class_template['class_name'].tolist()

        def get_teacher(subject: str):
            for s_t in subject_teacher:
                if subject in s_t[1].split('/'):
                    if teacher_flag:
                        return s_t[0]
                    else:
                        return subject[:2]
                        # return s_t[2]
            return subject
        # for t_s in subject_teacher:
        df_schedule[required_columns] = df_schedule[required_columns].map(
            lambda x: get_teacher(x) if isinstance(x, str) else x)
        return df_schedule

    def update_schedule(self, id: int, title: str, schedule_file: str) -> int:
        """
        更新课表
        返回值：
            0：更新失败
            1：更新本周课表，通知所有老师
            5：本周课表微调，只通知相关老师
            10：更新下周课表，通知所有老师，并生成下周课表
        """
        # 更新课表
        # schedule_file = "c:\\Users\\Administrator\\Desktop\\schedule.xlsx"
        # 检查文件的名称是否符合要求
        UPDATE_CURRENT_WEEK = 1
        UPDATE_CURRENT_WEEK_MINOR = 5
        UPDATE_NEXT_WEEK = 10
        UPDATE_FAILED = 0

        if title not in [self.week_info[1], self.week_info[1]+'微调', self.week_next[1]+'下周']:
            self.notify_admins(f'课表日期错误，请检查')
            return UPDATE_FAILED
        if title == self.week_next[1]+'下周':  # 下周新课表将通知所有老师
            return_flag = UPDATE_NEXT_WEEK
            _current_schedule_file = self.current_schedule_file(week_next=True)
            title = self.week_next[1]
        elif title == self.week_info[1]:  # 本周新课表将通知所有老师
            return_flag = UPDATE_CURRENT_WEEK
            _current_schedule_file = self.current_schedule_file()
        elif title == self.week_info[1]+'微调':  # 本周课表微调，只通知相关老师
            return_flag = UPDATE_CURRENT_WEEK_MINOR
            title = self.week_info[1]
            _current_schedule_file = self.current_schedule_file()
        else:
            return UPDATE_FAILED
        # print(return_flag)
        schedule_dir = os.path.join(
            self.lesson_dir, self.current_month, 'class_schedule')
        if not os.path.exists(schedule_dir):
            log.error(f"目录 {schedule_dir} 不存在")
            self.notify_admins(f'目录 {schedule_dir} 不存在')
            return UPDATE_FAILED
        # 将原来的文件移动到 schedule_history 文件
        try:
            # 将新的课表文件复制到 class_schedule 文件
            try:
                schedule_dir = os.path.join(
                    self.lesson_dir, self.current_month, 'class_schedule')
                history_dir = os.path.join(
                    self.lesson_dir, self.current_month, 'schedule_history')
                new_schedule = f'课表{title}-{int(time.time())}.xlsx'
                new_schedule_file = os.path.join(schedule_dir, new_schedule)
                data = {"id": int(id), "extra": schedule_file,
                        "dst": new_schedule_file}
                # data = {"id": id, "extra": schedule_file,"dst": "d:/abc.xlsx"}
                q = QueueDB()
                q.token = q.get_token(Config().get_config('wcf_admin'), Config().get_config('wcf_pwd'))
                headers = {
                    'accept': 'application/json',
                    'Content-Type': 'application/json',
                    'Authorization': f'Bearer {q.token}'
                }
                # 下载新课表到指定位置 class_schedule
                # 发送请求，最多重试3次
                wcf = Config().get_config('wcf_http_url')+'save-file'
                response = None
                max_retries = 3

                for attempt in range(max_retries):
                    try:
                        response = requests.post(
                            wcf, data=json.dumps(data), headers=headers)
                        print('-------------------------------')
                        print(response)
                        print(response.text)
                        print(attempt, time.time())
                        print('-------------------------------')
                        if response.text != '':
                            break
                        log.warning(f"请求失败，尝试第 {attempt + 1} 次重试")
                        if attempt < max_retries - 1:
                            time.sleep(3)  # 每次重试前等待1秒
                    except Exception as e:
                        log.error(f"请求发生错误: {str(e)}")
                        if attempt < max_retries - 1:
                            time.sleep(3)

                if not response or not response.text or response.text == '':
                    self.notify_admins('请求失败，请重新发送课表文件！')
                    return UPDATE_FAILED

                response_path = os.path.normpath(json.loads(response.text))
                new_path = os.path.normpath(new_schedule_file)
                log.info(f"下载的课表文件：{response_path}, 新课表文件：{new_path}")
                if response_path == new_path:
                    if return_flag == 10:
                        result = self.check_schedule(
                            new_path, week_next=True, ignore=True)
                    else:
                        result = self.check_schedule(
                            new_path, week_next=False, ignore=True)
                    if result == 'ok':
                        if _current_schedule_file != '':
                            # 新课表没有问题，将原来的课表移动到 schedule_history，移动过程出错
                            if not self.move_file(_current_schedule_file, history_dir):
                                log.error(f"更新课表失败，无法移动到 schedule_history")
                                self.notify_admins(
                                    f'更新课表失败，无法移动到 schedule_history')
                                return UPDATE_FAILED
                            else:
                                # 新课表没有问题，课表更新成功
                                self.notify_admins(f'课表已更新:{new_schedule}')
                                log.info(f'课表已更新:{new_schedule}')
                                self.refresh_cache()
                                return return_flag
                        else:
                            self.notify_admins(
                                f'当前没有课表文件, 是一个新课表: {new_schedule}')
                            return return_flag
                    else:
                        self.notify_admins(f'更新课表失败，{result}')
                        # 新课表有问题，将下载的新课表 删除
                        try:
                            os.chmod(new_path, 0o777)
                            os.remove(new_path)
                            self.notify_admins(f'更新课表失败，已删除{new_path}')
                        except FileNotFoundError:
                            self.notify_admins(f'更新课表失败，{new_path}文件未找到')
                        except PermissionError:
                            self.notify_admins(f'更新课表失败，{new_path}没有权限删除')
                        except Exception as e:
                            self.notify_admins(f'删除{new_path}失败，{e}')
                        return UPDATE_FAILED
                else:
                    log.error(f"更新课表失败，路径不一致，无法复制到 class_schedule")
                    self.notify_admins(f'更新课表失败，路径不一致，无法复制到 class_schedule')
                    return UPDATE_FAILED
            except Exception as e:
                log.error(f"更新课表时发生错误: {str(e)}")
                self.notify_admins(f'更新课表时发生错误: {str(e)}')
                return UPDATE_FAILED
        except Exception as e:
            log.error(f"无法找到课表. {e}")
            self.notify_admins(f'无法找到课表. {e}')
            return UPDATE_FAILED

    def _check_schedule_date(self, df: pd.DataFrame, week_info: list) -> str:
        """检查课表日期是否正确"""
        try:
            if 'date' not in df.columns:
                log.error(self.ERROR_MESSAGES['DATE_NOT_FOUND'])
                return 'schedule_date_error'

            monday = week_info[1]
            date_list = [int(datetime.strptime(
                monday, '%Y%m%d').strftime('%d'))]
            for i in range(1, 7):
                date_list.append(
                    int((datetime.strptime(monday, '%Y%m%d') +
                        timedelta(days=i)).strftime('%d'))
                )

            df_date = df['date'].astype(int).tolist()
            df_date = list(dict.fromkeys(df_date))

            invalid_dates = [d for d in df_date if d not in date_list]
            if invalid_dates:
                error_msg = self.ERROR_MESSAGES['DATE_INVALID'].format(
                    invalid_dates)
                log.error(error_msg)
                return 'schedule_date_error'

            return 'ok'

        except Exception as e:
            log.error(
                self.ERROR_MESSAGES['SCHEDULE_CHECK_FAILED'].format(str(e)))
            return 'schedule_date_error'

    def _check_schedule_class(self, df: pd.DataFrame) -> str:
        """检查课表班级列是否完整"""
        if self.class_template is None:
            return 'ok'
        required_columns = self.class_template['class_name'].tolist()
        missing_columns = [
            col for col in required_columns if col not in df.columns]

        if missing_columns:
            error_msg = self.ERROR_MESSAGES['MISSING_COLUMNS'].format(
                ', '.join(missing_columns))
            log.error(error_msg)
            return 'schedule_class_error'

        return 'ok'

    def _check_repeated_subjects(self, df: pd.DataFrame, ignore: bool = False) -> str:
        """检查课表中是否有重复的科目"""
        df_teacher = self.repalce_subject_teacher(df, ignore=ignore)
        df_subject = self.format_schedule(df, ignore=ignore)
        if self.class_template is None:
            return 'class_template Error'
        class_list = self.class_template['class_name'].tolist()
        df_class = df_teacher[class_list]

        # 获取可以跳过重复检测的科目
        repeated = pd.read_excel(
            os.path.join(self.lesson_dir, 'checkTemplate.xlsx'),
            sheet_name='repeated',
            engine='openpyxl'
        )['subject'].tolist()

        repeated_lines = []
        for index, row in df_class.iterrows():
            duplicates = row[row.duplicated()].to_dict()
            if duplicates:
                for k, v in duplicates.items():
                    if v != '-':
                        subject = df_subject.loc[index, k]
                        if subject not in repeated:
                            repeated_lines.append(f"第{index + 2}行: {k} - {v}")

        if repeated_lines:
            error_msg = self.ERROR_MESSAGES['REPEATED_SUBJECTS'].format(
                '\n'.join(repeated_lines))
            log.error(error_msg)
            return f'schedule_repeated_error:{error_msg}'

        return 'ok'

    def check_schedule(self, schedule_file: str, week_next: bool = False, ignore: bool = False) -> str:
        """
        检查课表是否符合要求

        Args:
            schedule_file: 课表文件路径
            week_next: 是否检查下周课表

        Returns:
            str: 检查结果，'ok'表示通过，其他值表示错误信息
        """
        try:
            df = pd.read_excel(schedule_file)
            week_info = self.week_next if week_next else self.week_info

            # 检查日期
            result = self._check_schedule_date(df, week_info)
            if result != 'ok':
                return result

            # 检查班级列
            result = self._check_schedule_class(df)
            if result != 'ok':
                return result

            # 检查重复科目
            result = self._check_repeated_subjects(df, ignore=ignore)
            if result != 'ok':
                return result

            return 'ok'

        except Exception as e:
            error_msg = self.ERROR_MESSAGES['SCHEDULE_CHECK_FAILED'].format(
                str(e))
            log.error(error_msg)
            return error_msg

    @staticmethod
    def sorted_schedule_file(path: str, monday: str) -> list:
        """
        获取排序后的课表文件列表

        Args:
            path: 课表文件目录
            monday: 周一日期

        Returns:
            list: 排序后的课表文件列表
        """
        try:
            # 预编译正则表达式模式
            timestamp_pattern = re.compile(r'-(\d+)')

            # 使用列表推导式过滤文件
            schedule_files = [
                s for s in os.listdir(path)
                if monday in s
            ]

            if not schedule_files:
                return []

            def extract_timestamp(filename: str) -> int:
                """从文件名中提取时间戳"""
                match = timestamp_pattern.search(filename)
                return int(match.group(1)) if match else 0

            # 使用key函数优化排序
            return sorted(
                schedule_files,
                key=extract_timestamp,
                reverse=True
            )

        except Exception as e:
            log.error(f"排序课表文件失败: {str(e)}")
            return []

    # TODO: 优化返回的数据，只通知老师 调课的日期和班级
    def schedule_diff(self, old_schedule_file: str = None, new_schedule_file: str = None, ignore: bool = False):
        """
        该方法 局限性比较强， 不建议使用
        """
        # 读取新旧课表， 并进行格式化，替换成老师和科目
        if new_schedule_file is None:
            monday = self.week_info[1]
            schedule_dir = os.path.join(
                self.lesson_dir, self.current_month, 'class_schedule')
            new_schedule_file = os.path.join(
                schedule_dir, self.sorted_schedule_file(schedule_dir, monday)[0])
        if old_schedule_file is None:
            # 如果 old_schedule_file 为空，则 查找之前的课表
            monday = self.week_info[1]
            history_dir = os.path.join(
                self.lesson_dir, self.current_month, 'schedule_history')
            old_schedule_file = os.path.join(
                history_dir, self.sorted_schedule_file(history_dir, monday)[0])
        old_df = pd.read_excel(old_schedule_file)
        new_df = pd.read_excel(new_schedule_file)
        # print(new_schedule_file, old_schedule_file)
        old_df_teacher = self.repalce_subject_teacher(old_df, ignore=ignore)
        new_df_teacher = self.repalce_subject_teacher(new_df, ignore=ignore)
        class_list = self.class_template['class_name'].tolist()
        # 创建一个与new_df相同形状的DataFrame来存储差异
        diff_df = pd.DataFrame(index=new_df.index, columns=new_df.columns)

        # 比较old_df和new_df，标记不同的单元格
        for col in class_list:
            for idx in new_df_teacher.index:
                if old_df_teacher.loc[idx, col] != new_df_teacher.loc[idx, col]:
                    diff_df.loc[idx,
                                col] = f"{old_df_teacher.loc[idx, col]} -> {new_df_teacher.loc[idx, col]}"
                # else:
                #     diff_df_teacher.loc[idx, col] = new_df_teacher.loc[idx, col]

        # 将差异DataFrame转换为字典，方便后续处理
        diff_dict = diff_df.to_dict()

        # 创建一个列表来存储所有的变更
        changes = []

        # 遍历差异字典，收集所有的变更
        for col, row_dict in diff_dict.items():
            for idx, value in row_dict.items():
                if '->' in str(value):
                    old, new = value.split(' -> ')
                    date = new_df.loc[idx, 'date']
                    week = new_df.loc[idx, 'week']
                    order = new_df.loc[idx, 'order']
                    changes.append([idx, col, date, order, old, new, week])

        # 将变更 按照 班级和老师 进行分类
        class_changes = []  # 通知班主任
        for change in changes:
            category = change[1]
            if category not in class_changes:
                class_changes.append(category)

        diff_teachers = []  # 通知老师
        for change in changes:
            old_category = change[4]
            new_category = change[5]
            if old_category not in diff_teachers:
                teacher = self.get_subject_teacher(old_category)
                diff_teachers.append(teacher)
            if new_category not in diff_teachers:
                teacher = self.get_subject_teacher(new_category)
                diff_teachers.append(teacher)
        return class_changes, diff_teachers

    # 返回班级课表的 df， 生成的图片由df_to_png生成
    def get_class_schedule(self, class_name: str, week_next: bool = False):
        if week_next:
            current_schedule_file = self.current_schedule_file(week_next=True)
            class_name = class_name.replace('下周', '')
        else:
            current_schedule_file = self.current_schedule_file()

        try:
            # Read the current schedule file and keep only the required columns
            required_columns = ['date', 'week', 'order', class_name]
            df = pd.read_excel(current_schedule_file)
            df = self.repalce_subject_teacher(
                df, teacher_flag=False, week_next=week_next, ignore=False)
            df = df[required_columns]
            # Group by 'week' and aggregate class_name into a list
            grouped_df = df.groupby(
                'week')[class_name].apply(list).reset_index()
            # Create a new DataFrame with 'week' as columns and corresponding class_name values
            new_df = pd.DataFrame(
                grouped_df[class_name].tolist(), index=grouped_df['week'])
            new_df.columns = df['order'][:new_df.shape[1]]
            new_df.index.name = '星期'
            new_df.columns.name = '节次'
            new_df = new_df.map(lambda x: '-' if x is None else x)
            return new_df.T
        except Exception as e:
            log.error(f"Error processing schedule file: {e}")
            return None

    def df_to_png(self, df: pd.DataFrame, png_name: str = "temp.png", title: str = ''):
        """将df转换为png图片"""
        try:
            df.index.name = '节次\星期'
            df.reset_index(inplace=True)
        except Exception as e:
            log.error(f"Error processing schedule file: {e}")
        lines = len(df.index) + 2
        css = '''
            table {
                border-collapse: collapse;
                width: 100%;
                margin-left: auto;
                margin-right: auto;
            }

            th, td {
                text-align: center;
                border: 1px solid #333333;
                padding: 4px;
            }

            th {
                background-color: #4573E9;
                color: #ffffff;
            }
            tr:nth-child(even) {
            background-color: #e8e8e8;
            }
            .score {
                color: #5fba7d;
                font-weight: bold;
            }
        '''
        html = df.to_html(classes='table', index=False, index_names=False, escape=False, table_id='example', na_rep='-',
                          float_format='%.2f', justify='center', col_space=30)

        with open(os.path.join(self.lesson_dir, 'temp', f'{png_name}.html'), 'w') as f:
            f.write(f'<h2 style="text-align: center;">{title}</h2>\n')
            f.write('<style>{}</style>\n{}'.format(css, html))

        with open(os.path.join(self.lesson_dir, 'temp', f'{png_name}.html'), 'r') as f:
            html_code = f.read()

        hti = Html2Image()
        hti.browser.flags = ['--headless=new']

        hti.size = (1440, 35 * lines + 50)
        hti.output_path = os.path.join(self.lesson_dir, 'temp')
        image = hti.screenshot(html_code, save_as=png_name)
        return image

    def get_teacher_schedule(self, teacher_name: str, week_next: bool = False) -> pd.DataFrame:
        """获取老师的课表"""
        if week_next:
            current_schedule_file = self.current_schedule_file(week_next=True)
        else:
            current_schedule_file = self.current_schedule_file()
        df = pd.read_excel(current_schedule_file, engine='openpyxl')
        df_subject = self.repalce_subject_teacher(
            df, teacher_flag=False, week_next=week_next)
        df = self.repalce_subject_teacher(
            df, teacher_flag=True, week_next=week_next)
        grouped_df = df[['week', 'order']].groupby('week')
        # Find the group with the maximum length
        max_length_group = max(grouped_df, key=lambda x: len(x[1]))
        max_length_week = max_length_group[0]
        # Filter the DataFrame to only include rows from the max length week
        schedule_order = df[df['week'] == max_length_week]['order'].tolist()
        week_list = list(grouped_df.groups.keys())
        teacher_df = pd.DataFrame(columns=week_list, index=schedule_order)
        # Filter the DataFrame to only include rows where the teacher is present
        teacher_schedule = df[df.isin([teacher_name]).any(axis=1)]
        # print(teacher_schedule)
        for index, row in teacher_schedule.iterrows():
            # print(index)
            week = row['week']
            order = row['order']
            teacher_column = row.index[row == teacher_name][0]
            teacher_subject = df_subject.loc[index, teacher_column]
            teacher_df.loc[order,
                           week] = f"{teacher_column}-{teacher_subject}" if teacher_subject else teacher_column
        return teacher_df

    def today_schedule(self) -> pd.DataFrame:
        """获取今天的课表"""
        print(self._current_schedule_file)
        df = pd.read_excel(self._current_schedule_file)
        df = self.format_schedule(df)
        df['date'] = df['date'].astype(str)
        today = str(int(datetime.today().strftime('%d')))
        # print(today)
        today_df = df[df['date'] == today]
        return today_df

    def current_schedule(self) -> dict:
        """获取当前正在上课的课程"""
        df = self.today_schedule()
        current_time = datetime.now().strftime("%H:%M")
        current_classes = {}
        current_period = None
        periods = {order: show_time for order, show_time in zip(
            self.time_table['order'], self.time_table['show_time'])}
        for period, time_range in periods.items():
            start_time, end_time = time_range.split("-")
            # 将时间字符串转换为分钟数，以便进行比较
            start_minutes = sum(int(x) * 60 ** i for i,
                                x in enumerate(reversed(start_time.split(":"))))
            end_minutes = sum(int(x) * 60 ** i for i,
                              x in enumerate(reversed(end_time.split(":"))))
            current_minutes = sum(
                int(x) * 60 ** i for i, x in enumerate(reversed(current_time.split(":"))))

            if start_minutes <= current_minutes <= end_minutes:
                current_period = period
                break
        if current_period is not None:
            df_current = df[df['order'] == current_period]
            for class_name in self.class_template['class_name'].tolist():
                current_classes[class_name] = df_current[class_name].values[0]
        return current_classes

async def create_month_dir():
    """
    每个月的1号，将上个月的课表复制到 新月份 的目录下
    """
    l = Lesson()
    try:
        current_dir = l.create_c_month_dir()
        if current_dir:
            log.info(f"创建目录成功: {current_dir}")
        else:
            log.error("创建目录失败")
            return False
    except Exception as e:
        log.error(f"创建目录时出错: {str(e)}")
        return False
    c_month = current_dir.split('/')[-1]
    # c_month = "202501"
    year = int(c_month[:4])
    month = int(c_month[4:])
    if month == 1:
        p_month = f"{year-1}12"
    else:
        p_month = f"{year}{month-1:02d}"

    # 将上月的课表复制到新月份的目录下
    p_month_dir = os.path.join(l.lesson_dir, p_month)
    c_month_dir = os.path.join(l.lesson_dir, c_month)
    schedule_list = os.listdir(os.path.join(p_month_dir, 'class_schedule'))
    time_flag = 0
    schedule_file = ''
    for schedule in schedule_list:
        timestamp = int(schedule.split('-')[-1].split('.')[0])
        if timestamp > time_flag:
            time_flag = timestamp
            schedule_file = schedule
    if schedule_file:
        shutil.copy(os.path.join(p_month_dir, 'class_schedule', schedule_file),
                    os.path.join(c_month_dir, 'class_schedule', schedule_file))
        log.info(f"月初以复制课表文件成功: {schedule_file}")
        return True
    else:
        log.error("未找到文件")
        return False


async def update_schedule(record: any):
    content = record.content
    title = re.match(r'^\[文件\] <课表(\d{8}.*)\.xlsx>$', content).group(1)
    if title:
        l = Lesson()
        result = l.update_schedule(record.id, title, record.extra)
        if result == 1:
            # '通知所有老师本周课表变动'
            for a in l.admin:
                send_remind('更新所有人的课表', a)
        elif result == 10:
            # '通知所有老师下周课表变动'
            for a in l.admin:
                send_remind('更新下周的课表', a)
        elif result == 5:
            teachers = []
            # '通知相关老师课表变动'
            diffs = l.schedule_diff()
            if diffs != ([], []):
                class_diff = diffs[0]
                teachers_diff = diffs[1]
                flag = 1
                for k in class_diff:
                    class_df = l.get_class_schedule(k)
                    title = f'{k}的课表'
                    class_pic = l.df_to_png(
                        class_df, f'class_{str(flag)}.png', title=title)[0]
                    flag += 1
                    wxids = l.get_wxids(k)
                    teachers.append(k)
                    for wxid in wxids:
                        send_remind(f"你们班：有调课请注意查看！", wxid)
                        if class_pic:
                            send_image(class_pic, wxid, 'lesson')
                for k in teachers_diff:
                    teacher_df = l.get_teacher_schedule(k)
                    title = f'{k}的课表'
                    wxids = l.get_wxids(k)
                    teachers.append(k)
                    for wxid in wxids:
                        send_remind(f"你的课有调整，请注意查看！", wxid)
                        teacher_pic = l.df_to_png(
                            teacher_df, f'{wxid}.png', title=title)[0]
                        if teacher_pic:
                            send_image(teacher_pic, wxid, 'lesson')
                teachers = set(teachers)
                tips = '微调课表已通知以下老师:'
                for teacher in teachers:
                    tips += f'\n{teacher}'
                l.notify_admins(tips)
        else:
            return '更新课表失败'


async def update_schedule_all(record: any):
    """
    更新所有人的课表
    """
    # content = record.content
    # l = Lesson()
    # contacts = l.contacts
    # class_leaders = l.class_template[['class_name', 'class_en']]
    # leaders_dict = dict(
    #     zip(class_leaders['class_name'], class_leaders['class_en']))
    # teacher_name = re.match(r'^(.+?)\s*的课表$', content).group(1)

    # # 生产课表失败的 教师或班级
    # err = ""

    # def check_image_size(image_path, min_size=5*1024):  # 5KB
    #     """检查图片大小是否小于最小值"""
    #     return os.path.getsize(image_path) < min_size

    # def process_teacher_schedule(teacher_name, wxid, week_next=False, err=err):
    #     try:
    #         df = l.get_teacher_schedule(teacher_name, week_next=week_next)
    #         if df.empty:
    #             for a in l.admin:
    #                 send_remind(f'{teacher_name}的课表不存在', a)
    #         else:
    #             schedule_file = l.current_schedule_file(week_next=week_next)
    #             df_png = l.df_to_png(
    #                 df, f'{wxid}.png', title=f'{teacher_name}{"下周" if week_next else ""}的课表')[0]
    #             if check_image_size(df_png):
    #                 print(f'老师 {teacher_name} 的课表图片为空，正在重新生成...')
    #                 df_png = l.df_to_png(
    #                     df, f'{wxid}.png', title=f'{teacher_name}{"下周" if week_next else ""}的课表')[0]
    #             send_image(df_png, wxid, 'lesson')
    #             send_file(schedule_file, wxid, 'lesson')
    #     except Exception as e:
    #         err += f'{teacher_name}-'
    #         print(f'处理老师 {teacher_name} 的课表时发生错误: {e}')

    # def process_class_schedule(class_name, v, week_next=False, err=err):
    #     try:
    #         class_df = l.get_class_schedule(class_name, week_next=week_next)
    #         title = f'{class_name}{"下周" if week_next else ""}的课表'
    #         if not class_df.empty:
    #             class_pic = l.df_to_png(
    #                 class_df, f'class_{v}.png', title=title)[0]
    #             if check_image_size(class_pic):
    #                 print(f'班级 {class_name} 的课表图片为空，正在重新生成...')
    #                 class_pic = l.df_to_png(
    #                     class_df, f'class_{v}.png', title=title)[0]
    #             if class_pic:
    #                 wxids = l.get_wxids(class_name)
    #                 for wxid in wxids:
    #                     send_image(class_pic, wxid, 'lesson')
    #     except Exception as e:
    #         err += f'{class_name}-'
    #         print(f'处理班级 {class_name} 的课表时发生错误: {e}')

    # if teacher_name == '更新所有人':
        # with concurrent.futures.ThreadPoolExecutor() as executor:
    #         # 并行处理所有老师的课表
    #         future_to_teacher = {executor.submit(
    #             process_teacher_schedule, k, v, False): k for k, v in contacts.items()}
    #         for future in concurrent.futures.as_completed(future_to_teacher):
    #             teacher_name = future_to_teacher[future]
    #             try:
    #                 future.result()
    #             except Exception as exc:
    #                 print(f'老师 {teacher_name} 生成课表图片时发生异常: {exc}')

    #         # 并行处理所有班级的课表
    #         future_to_class = {executor.submit(
    #             process_class_schedule, k, v, False): k for k, v in leaders_dict.items()}
    #         for future in concurrent.futures.as_completed(future_to_class):
    #             class_name = future_to_class[future]
    #             try:
    #                 future.result()
    #             except Exception as exc:
    #                 print(f'班级 {class_name} 生成课表图片时发生异常: {exc}')
    # elif teacher_name == '更新下周':
    #     with concurrent.futures.ThreadPoolExecutor() as executor:
    #         # 并行处理所有老师的下周课表
    #         future_to_teacher_next = {executor.submit(
    #             process_teacher_schedule, k, v, True): k for k, v in contacts.items()}
    #         for future in concurrent.futures.as_completed(future_to_teacher_next):
    #             teacher_name = future_to_teacher_next[future]
    #             try:
    #                 future.result()
    #             except Exception as exc:
    #                 print(f'老师 {teacher_name} 生成下周课表图片时发生异常: {exc}')

    #         # 并行处理所有班级的下周课表
    #         future_to_class_next = {executor.submit(
    #             process_class_schedule, k, v, True): k for k, v in leaders_dict.items()}
    #         for future in concurrent.futures.as_completed(future_to_class_next):
    #             class_name = future_to_class_next[future]
    #             try:
    #                 future.result()
    #             except Exception as exc:
    #                 print(f'班级 {class_name} 生成下周课表图片时发生异常: {exc}')
    content = record.content
    l = Lesson()
    contacts = l.contacts
    class_leaders = l.class_template[['class_name', 'class_en']] # 班级列表
    leaders_dict = dict(zip(class_leaders['class_name'], class_leaders['class_en'])) # 班级-班级名称en
    teacher_name = re.match(r'^(.+?)\s*的课表$', content).group(1)
    if teacher_name == '更新所有人':
        # 通知所有老师
        for k, v in contacts.items():
            teacher_name = k
            wxid = v
            df = l.get_teacher_schedule(teacher_name)
            if df.empty:
                for a in l.admin:
                    send_remind(f'{teacher_name}的课表不存在', a)
            else:
                df_png = l.df_to_png(df, f'{wxid}.png', title=f'{teacher_name}的课表')[0]
                send_image(df_png, wxid, 'lesson')
        # 通知班主任班级课表
        for k, v in leaders_dict.items():
            class_df = l.get_class_schedule(k)
            title = f'{k}的课表'
            class_pic = l.df_to_png(class_df, f'class_{v}.png', title=title)[0]
            if class_pic:
                wxids = l.get_wxids(k)
                for wxid in wxids:
                    send_image(class_pic, wxid, 'lesson')
    elif teacher_name == '更新下周':
        # 通知所有老师
        for k, v in contacts.items():
            teacher_name = k
            wxid = v
            df = l.get_teacher_schedule(teacher_name, week_next=True)
            if df.empty:
                for a in l.admin:
                    send_remind(f'{teacher_name}的课表不存在', a)
            else:
                df_png = l.df_to_png(df, f'{wxid}.png', title=f'{teacher_name}下周的课表')[0]
                send_image(df_png, wxid, 'lesson')
        # 通知班主任班级课表
        for k, v in leaders_dict.items():
            class_df = l.get_class_schedule(k, week_next=True)
            title = f'{k}下周的课表'
            class_pic = l.df_to_png(class_df, f'class_{v}.png', title=title)[0]
            if class_pic:
                wxids = l.get_wxids(k)
                for wxid in wxids:
                    send_image(class_pic, wxid, 'lesson')

@check_permission
async def teacher_schedule(record: any):
    """
    获取老师(班级)课表
    1. 获取老师本人课表：我的课表
    2. 获取指定老师课表：张亚琦的课表
    3. 获取班级课表：高一3班的课表
    """
    content = record.content
    if len(content) > 9:
        return
    wxid = record.roomid
    l = Lesson()
    teacher_name = re.match(r'^(.+?)\s*的课表$', content).group(1)
    if teacher_name == '我' or teacher_name == '我下周':
        if teacher_name == '我下周':
            week_next = True
            teacher_name = teacher_name.replace('下周', '')
        else:
            week_next = False
        # 根据wxid获取老师名称
        wxid = record.roomid
        for k, v in l.contacts.items():
            if v == wxid:
                teacher_name = k
                break
        df = l.get_teacher_schedule(teacher_name, week_next=week_next)
        if df.empty:
            send_remind(f'{teacher_name}的课表不存在', wxid)
        else:
            if week_next:
                title = f'{teacher_name}下周的课表'
            else:
                title = f'{teacher_name}的课表'
            df_png = l.df_to_png(df, f'{wxid}.png', title=title)[0]
            send_image(df_png, wxid, 'lesson')
    elif teacher_name[0] == '高' and (teacher_name[-1] == '班' or teacher_name[-3:] == '班下周'):
        if teacher_name[-3:] == '班下周':
            week_next = True
            # teacher_name = teacher_name.replace('下周', '')
        else:
            week_next = False
        class_df = l.get_class_schedule(teacher_name, week_next=week_next)
        df_png = l.df_to_png(
            class_df, f'{wxid}.png', title=f'{teacher_name}的课表')[0]
        if not df_png:
            send_remind(f'{teacher_name}的课表不存在', wxid)
        else:
            send_image(df_png, wxid, 'lesson')
    else:
        if '下周' in teacher_name:
            week_next = True
            teacher_name = teacher_name.replace('下周', '')
        else:
            week_next = False
        df = l.get_teacher_schedule(teacher_name, week_next=week_next)
        if df.empty:
            send_remind(f'{teacher_name}的课表不存在', wxid)
        else:
            if week_next:
                title = f'{teacher_name}下周的课表'
            else:
                title = f'{teacher_name}的课表'
            df_png = l.df_to_png(df, f'{wxid}.png', title=title)[0]
            send_image(df_png, wxid, 'lesson')

@check_permission
async def get_current_schedule(record: any):
    content = record.content
    wxid = record.roomid
    l = Lesson()
    schedule_file = ''
    if content == '当前课表':
        schedule_file = l.current_schedule_file()
    if content == '下周课表':
        schedule_file = l.current_schedule_file(week_next=True)
    if schedule_file == '':
        send_remind(f'{content}还没有排好，请耐心等待', wxid)
        return
    # temp_file = os.path.join(l.lesson_dir, 'temp', 'KE_ALL.xlsx')
    # shutil.copy(schedule_file, temp_file)
    os.chmod(schedule_file, 0o777)
    file_name = schedule_file.split('课表')[-1]
    temp_file = os.path.join(l.lesson_dir, 'temp', file_name)
    shutil.copy(schedule_file, temp_file)
    os.chmod(temp_file, 0o777)
    send_file(temp_file, wxid)


def send_today_schedule(df, wxid):
    today_df = df
    l = Lesson()
    if today_df.empty:
        send_remind('今日无课', wxid)
    else:
        today = datetime.today().strftime('%Y-%m-%d')
        today_df.drop(['style', 'date', 'week'], axis=1, inplace=True)
        today_df = today_df.set_index('order')
        # 自定义函数，截取字符串的前四个字符,以免生产图片的时候显示不全

        def take_first_four(x):
            if isinstance(x, str) and len(x) >= 4:
                return x[:4]
            return x

        # 应用函数到DataFrame的每个元素
        today_df = today_df.map(take_first_four)
        df_png = l.df_to_png(
            today_df, f'{wxid}.png', title=f'{today}课表')[0]
        send_image(df_png, wxid, 'lesson')


async def refresh_schedule(record=None):
    l = Lesson()
    l.refresh_cache()
    today_df = l.today_schedule()
    try:
        wxid = record.roomid
    except Exception as e:
        wxid = l.admin[0]
    send_today_schedule(today_df, wxid)

@check_permission
async def get_today_schedule(record: any):
    l = Lesson()
    today_df = l.today_schedule()
    send_today_schedule(today_df, record.roomid)

@check_permission
async def get_current_teacher(record: any):
    l = Lesson()
    teachers = l.current_schedule()
    if teachers == {}:
        send_remind('当前没有老师正在上课！', record.roomid)
    else:
        tips = '当前上课老师如下:'
        for k, v in teachers.items():
            tips += f'\n{k}:{v}'
        send_remind(tips, record.roomid)


def today_teachers():
    l = Lesson()
    today_df = l.today_schedule()
    if today_df.empty:
        return
    today_df['order'] = today_df['order'].astype(str)
    class_order = l.time_table['order'].tolist()
    teachers = {}
    l = Lesson()
    today_df = l.today_schedule()
    if today_df.empty:
        print('今日无课')
        exit()
    today_df['order'] = today_df['order'].astype(str)
    class_order = l.time_table['order'].tolist()
    teachers = {}
    for order in class_order:
        for class_name in l.class_template['class_name'].tolist():
            class_df = today_df[[class_name, 'order']]
            try:
                subjcet = class_df[class_df['order'] ==
                                   str(order)][class_name].values[0]
                teacher = l.get_subject_teacher(subjcet)
                order_label = l.time_table[l.time_table['order']
                                           == order]['label'].values[0]
                if teacher not in teachers:
                    teachers[teacher] = []
                teachers[teacher].append(
                    f'{order_label}:{class_name} {subjcet[:2]}')
            except Exception as e:
                print(e, order, class_name)
    if not teachers:
        return
    for k, v in teachers.items():
        wxids = l.get_wxids(k)
        if wxids:
            wxid = l.get_wxids(k)[0]
            tips = f'您今天有{len(v)}节课如下:'
            for course in v:
                tips += f'\n{course}'
            # print(wxid, tips)
            send_remind(tips, wxid)

@check_permission
async def current_week_info(record: any):
    l = Lesson()
    week_info = l.week_info
    send_remind(str(week_info), record.roomid)

@check_permission
async def get_ip_info(record: any):
    content = record.content
    if content == '我的上网信息':
        wxid = record.roomid
        l = Lesson()
        ip_info = l.ip_info
        tips = '你的上网信息如下：\n'
        for k, v in l.contacts.items():
            if v == wxid:
                ip = ip_info.loc[k]
                tips += f"\n电脑认证账号：{ip['PC']}"
                tips += f"\n电脑设置IP：{ip['IP']}"
                tips += f"\nWiFi认证账号：{ip['WiFi']}"
        send_remind(tips, wxid)


def group_send(xlsx_file, sender):
    df = pd.read_excel(xlsx_file)
    cnt = 1
    l = Lesson()
    failed = []
    tips = ''
    for index, row in df.iterrows():
        name = row['接收人']
        try:
            wxids = l.get_wxids(name)
            for wxid in wxids:
                send_remind(f"{row['消息内容']}", wxid)
                log.info(f"{str(cnt)} {name} 已通知")
            cnt += 1
        except KeyError as e:
            log.error(f"KeyError: {str(e)}")
    tips = tips + f"已通知{str(cnt-1)}人\n"
    if failed:
        tips += '未通知以下人员：\n'
        for f in failed:
            tips += f"{f} "
    else:
        tips += '全部通知完毕！'

    send_remind(tips, sender)


async def mass_message(record: any):
    l = Lesson()
    content = record.content
    title = re.match(r'^\[文件\] <((学发|教发)群发通知\d*\.xlsx)>$', content).group(1)
    if title:
        title = title.split('.')[0]
        title = re.sub(r'\d+', '', title)
        notice_file = f'{title}-{time.strftime("%Y%m%d%H%M%S", time.localtime())}.xlsx'
        new_notice_file = os.path.join(l.lesson_dir, 'notice', notice_file)
        data = {"id": int(record.id), "extra": record.extra,
                "dst": new_notice_file}
        print(data)
        q = QueueDB()
        q.token = q.get_token(Config().get_config('wcf_admin'), Config().get_config('wcf_pwd'))
        headers = {
            'accept': 'application/json',
            'Content-Type': 'application/json',
            'Authorization': f'Bearer {q.token}'
        }
        # 下载新课表到指定位置 notice
        wcf = Config().get_config('wcf_http_url')+'save-file'
        response = requests.post(wcf, data=json.dumps(data), headers=headers)
        response_path = os.path.normpath(json.loads(response.text))
        print(response_path, '++++++')
        if response_path == '' or response_path == '.':
            send_remind('通知文件下载失败，请重新发送该文件！', record.roomid)
            return
        if response_path:
            os.chmod(response_path, 0o777)
            group_send(response_path, record.roomid)

@check_permission
async def file_template(record: any):
    """
    获取模板文件， 根据 file_template 文件配置 文件字典
    """
    file_name = record.content.replace('获取文件：', '').replace(' ','')
    file_template_path = Config().get_config('file_template')[file_name]
    l = Lesson()
    lesson_dir = l.lesson_dir
    template_file = os.path.join(lesson_dir, 'template', file_template_path) # API发送文件不支持中文path
    send_file(template_file, record.roomid)