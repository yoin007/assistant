# _*_ coding: utf-8 _*_
# @Time : 2024/09/26 14:50
# @Author : Tech_T


from function.lesson.lesson import refresh_schedule, today_teachers
from function.api import one_day_English, get_joke, get_weather, holiday
from function.parking import watching_parking
import asyncio
import datetime
import random
import time
import re


from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger
from openai import OpenAI

from sendqueue import QueueDB
from config.config import Config
from config.log import LogConfig
log = LogConfig().get_logger()
config = Config()


class Task(AsyncIOScheduler):
    def __init__(self):
        super().__init__()
        self.scheduler = AsyncIOScheduler()
        self.scheduler.configure(timezone='Asia/Shanghai')
        self.job_args = {}

    def add_job(self, func, trigger, *args, **kwargs):
        # 调用父类的add_job方法添加任务
        job = self.scheduler.add_job(func, trigger, *args, **kwargs)
        # 将任务的ID添加到jobs列表中
        if len(args) > 0:
            self.job_args[str(job.id)] = str(args[0][0])
        if len(kwargs) > 0:
            try:
                self.job_args[str(job.id)] = str(kwargs['kwargs']['func'])
            except:
                pass

    def add_job_cron(self, func, date_str, *args, **kwargs):
        year, month, day, hour, minute, second = parse_datetime(date_str)
        if year == 0:
            trigger = CronTrigger(hour=hour, minute=minute, second=second)
        else:
            trigger = CronTrigger(
                year=year, month=month, day=day, hour=hour, minute=minute, second=second)
        # print(trigger)
        self.add_job(func, trigger, *args, **kwargs)

    def add_job_interval(self, func, seconds, *args, **kwargs):
        trigger = IntervalTrigger(seconds=seconds, *args, **kwargs)
        # print(trigger)
        self.add_job(func, trigger, *args, **kwargs)

    def random_daily_task(self, func, start_time='00:00:00', end_time='23:59:59', *args, **kwargs):
        # 将字符串时间转换为datetime对象
        time_format = "%H:%M:%S"
        time_s = datetime.datetime.strptime(start_time, time_format)
        time_e = datetime.datetime.strptime(end_time, time_format)

        # 确保a在b之前
        if time_s > time_e:
            time_s, time_e = time_e, time_s

        # 计算时间差
        delta = time_e - time_s
        # 随机生成时间差
        random_seconds = random.randrange(int(delta.total_seconds()))
        # 生成随机时间
        random_time = time_s + datetime.timedelta(seconds=random_seconds)
        hour, minute, second = random_time.hour, random_time.minute, random_time.second
        # 计算下次运行的时间
        next_run_time = datetime.datetime.now().replace(
            hour=int(hour), minute=int(minute), second=int(second))
        # 如果下次运行的时间已经过去，则将时间设置为明天的同一时间
        if next_run_time < datetime.datetime.now():
            next_run_time += datetime.timedelta(days=1)

        # 更新任务的触发器
        trigger = CronTrigger(year=next_run_time.year, month=next_run_time.month, day=next_run_time.day,
                              hour=next_run_time.hour, minute=next_run_time.minute, second=next_run_time.second)

        # 添加任务
        self.scheduler.add_job(func, trigger, *args, **kwargs)
        # self.add_job(func, trigger, *args, **kwargs)

    def show_task(self) -> str:
        # 获取当前的日期和时间
        now = datetime.datetime.now()
        # 格式化日期和时间
        now_str = now.strftime('%H:%M:%S')
        tips = f"当前任务列表: {now_str}\n"
        cnt = 1
        for job in self.scheduler.get_jobs():
            try:
                arg = self.job_args[str(job.id)]
            except:
                arg = ''
            tips += f"{cnt}. {job.name}:\n{job.id}\n{arg}\n{job.trigger}\n"
            cnt += 1
        return tips

    def stop_task(self, job_id) -> str:
        try:
            # 从调度器中移除任务
            if job_id in self.job_args:
                del self.job_args[job_id]
                print(f"Key {job_id} has been removed from job_args.")
            else:
                print(f"Key {job_id} not found in job_args.")
            self.scheduler.remove_job(job_id)
            log.info(f'停止任务成功: {job_id}')
            return f'停止任务成功: {job_id}'
        except Exception as e:
            log.error(f'停止任务失败: {job_id}, 错误信息: {str(e)}')
            return f'停止任务失败: {job_id}, 错误信息: {str(e)}'

    async def start(self):
        # 启动调度器
        self.scheduler.start()

    async def stop(self):
        # 停止调度器
        self.scheduler.shutdown()

    async def run(self, duration: int):
        await self.start()
        await asyncio.sleep(duration)
        await self.stop()


def parse_datetime(date_str):
    # 解析字符串为datetime对象
    try:
        datetime_obj = datetime.datetime.strptime(date_str, '%Y%m%d %H:%M:%S')
        year = datetime_obj.year
        month = datetime_obj.month
        day = datetime_obj.day
    except ValueError:
        year, month, day = 0, 0, 0
        hms = re.findall(r':', date_str)
        if len(hms) == 2:
            datetime_obj = datetime.datetime.strptime(date_str, '%H:%M:%S')
        else:
            datetime_obj = datetime.datetime.strptime(date_str, '%H:%M')
    # 提取年月日时分秒
    hour = datetime_obj.hour
    minute = datetime_obj.minute
    second = datetime_obj.second
    # 返回年月日时分秒列表
    return [year, month, day, hour, minute, second]


def calculate_future_time(seconds):
    try:
        # 尝试直接将seconds转换为整数
        seconds = int(seconds)
    except ValueError:
        # 如果转换失败，尝试评估seconds表达式
        try:
            seconds = eval(seconds)
        except Exception as e:
            raise ValueError(f"无法解析参数 '{seconds}'。错误: {e}")

    # 获取当前时间
    current_time = datetime.datetime.now()
    # 计算x秒后的时间
    future_time = current_time + datetime.timedelta(seconds=seconds)
    # 格式化时间字符串
    time_str = future_time.strftime('%Y%m%d %H:%M:%S')
    return time_str


def send_remind(tips, receiver, produce='task'):
    mid = str(time.time().__int__())
    with QueueDB() as q:
        q.send_text(mid, tips, receiver, '', produce)
    time.sleep(1)


def water_remind():
    drink_water_reminders = [
        "喝水时间到，别忘了给身体补水哦！\n肩颈操5分钟，身体更健康！",
        "一杯清水，健康相随。\n深蹲50次",
        "让清水滋润你的每一天。\n胯下击掌50次",
        "喝水，让健康成为习惯。\ntabata",
        "记得喝水，保持活力满满。\n兔子舞",
        "一杯水，一份健康，一份快乐。\n八段锦",
        "喝水，是最简单的养生之道。\n拍打操",
        "清水一杯，健康相随。\n拉筋操",
        "别忘了，身体也需要“喝水”。\n座上操",
        "喝水，让肌肤更水润。\n原地跑",
        "一杯水，一份清新，一份健康。\n肩颈操5分钟，身体更健康！",
        "喝水，让生活更加美好。\n深蹲50次",
        "让清水成为你生活的一部分。\n胯下击掌50次",
        "喝水，让身体更健康。\ntabata",
        "一杯水，一份关怀，一份健康。\n兔子舞",
        "喝水，让心情更加舒畅。\n原地跑",
        "清水一杯，健康相伴。\n拉筋操",
        "喝水，让生活更加精彩。\n座上操",
        "别忘了，身体也需要水分。\n八段锦",
        "喝水，让健康成为你的朋友。\n拍打操",
        "一杯水，一份清新，一份快乐。\n拉筋操",
        "喝水，让身体更加充满活力。\n座上操"
    ]

    # 随机选取一个提醒
    random_reminder = random.choice(drink_water_reminders)
    joke = get_joke()
    tips = f"{random_reminder}\n\n看个笑话开心一下吧！\n{joke}"
    for r in config.get_config('gk_remind'):
        send_remind(tips, r)
        time.sleep(1)


def countdown_day(month, day):
    """
    日期倒计时函数
    :param target_date:
    :return:
    """
    # 获取当前日期
    today = datetime.datetime.now()

    # 设置高考日期为每年的6月7日
    college_entrance_exam_date = datetime.datetime(today.year, month, day)

    # 如果当前日期已经超过了今年的高考日期，则计算明年的高考日期
    if today > college_entrance_exam_date:
        college_entrance_exam_date = college_entrance_exam_date.replace(
            year=today.year + 1)

    # 计算倒计时天数
    delta = college_entrance_exam_date - today
    days_to_go = delta.days
    return days_to_go


def morning_hi(city='李沧'):
    holiday_tip = holiday()
    weather_report = get_weather(city)
    weather_tip = ''
    if weather_report:
        realtime = weather_report['realtime']
        weather = {'温度': realtime['temperature'], '湿度': realtime['humidity'], '天气': realtime['info'],
                   '风向': realtime['direct'], '风力': realtime['power'], '空气质量': realtime['aqi']}
        for k, v in weather.items():
            weather_tip = weather_tip + f'{k}：{v}\t'
        tips = holiday_tip + f'\n\n{city}今日天气：\n' + weather_tip
    else:
        tips = holiday_tip
    for r in config.get_config('gk_remind'):
        send_remind(tips, r)
        time.sleep(1)


def gk_countdown():
    """
    高考倒计时，每天一句英语
    :return:
    """
    morning_hi()
    year = datetime.datetime.now().year
    tips = one_day_English()

    gk_days = countdown_day(6, 7)
    zk_days = countdown_day(6, 13)
    if gk_days > 0:
        gk_tips = f"距离{str(year)}年高考还有{gk_days}天!"
    elif gk_days == 0:
        gk_tips = f"今日高考，祝考试顺利，金榜题名！"
    if zk_days > 0:
        zk_tips = f"距离{str(year)}年中考还有{zk_days}天!"
    elif zk_days == 0:
        zk_tips = f"今日中考，祝考试顺利，金榜题名！"

    msg = f"{tips}"
    msg = msg + '\n' + gk_tips + '\n' + zk_tips
    # print(msg)
    for r in config.get_config('gk_remind'):
        send_remind(msg, r)
        time.sleep(1)


task_scheduler = Task()


async def task_start():
    # 添加每日高考倒计时提醒
    task_scheduler.add_job(task_scheduler.random_daily_task, CronTrigger(hour=3), kwargs={
        'func': refresh_schedule, 'start_time': '07:11:02', 'end_time': '07:17:10'})
    task_scheduler.add_job(task_scheduler.random_daily_task, CronTrigger(hour=2), kwargs={
        'func': today_teachers, 'start_time': '07:20:02', 'end_time': '07:35:10'})
    task_scheduler.add_job(task_scheduler.random_daily_task, CronTrigger(hour=1), kwargs={
        'func': gk_countdown, 'start_time': '08:01:02', 'end_time': '08:14:10'})
    task_scheduler.add_job(watching_parking, IntervalTrigger(seconds=60))
    # task_scheduler.random_daily_task(
    # today_teachers, start_time='07:20:02', end_time='07:29:10')
    # task_scheduler.add_job(task_scheduler.random_daily_task, CronTrigger(hour=0), kwargs={'func': gk_countdown, 'start_time':'07:30:02', 'end_time':'07:49:10'})
    # task_scheduler.add_job_cron(morning_hi, '1206 15:22')
    # 喝水提醒
    water_time = ['09:40', '11:00', '14:15', '16:20']
    for t in water_time:
        task_scheduler.add_job_cron(water_remind, t)
    await task_scheduler.run(3600*24*30)


async def get_task_list(record: any):
    receiver = record.roomid
    tips = task_scheduler.show_task()
    send_remind(tips, receiver)


async def stop_task_job(record: any):
    receiver = record.roomid
    content = record.content
    job_id = re.match(r'^停止任务-(.*)', content).group(1)
    tips = task_scheduler.stop_task(job_id)
    send_remind(tips, receiver)


async def add_cron_remind(record: any, task_scheduler=task_scheduler):
    """
    添加定时 提醒任务
    定时-20240908 14:00:00-提醒内容
    """
    text = record.content
    now = datetime.datetime.now().strftime("%H:%M:%S")
    today = datetime.datetime.now().strftime("%Y%m%d")
    week_day = int(datetime.datetime.now().weekday()) + 1
    propmt = f'{text}\n把上面这句话按照下面的指定格式的字符串返回给我，请只返回格式化的字符串，不要其他内容。\n指定格式:定时-提醒日期和时间-提醒内容\n提醒日期和时间的格式为:YYYYMMDD HH:MM:SS\n当前日期是{today},当前时间是{now}，本周的第{str(week_day)}天，请以当前日期和当前时间正确计算提醒日期和时间，尤其是关于星期(周几)的计算(每周从周1开始，一周7天)'
    key = Config().get_config("deepseek_key")

    client = OpenAI(api_key=key, base_url="https://api.deepseek.com")

    response = client.chat.completions.create(
        model="deepseek-chat",
        messages=[
            {"role": "system", "content": "You are a helpful assistant"},
            {"role": "user", "content": propmt},
        ],
        max_tokens=1024,
        temperature=0.7,
        stream=False
    )

    text = str(response.choices[0].message.content)
    result = text.split('-')
    if len(result) == 3:
        date_str = result[1]
        tips = result[2]
        task_scheduler.add_job_cron(
            send_remind, date_str, [tips, record.roomid])
        send_remind(f'添加定时提醒任务: {date_str}, 提醒内容: {tips}', record.roomid)
    else:
        send_remind('添加定时提醒任务失败', record.roomid)


async def add_interval_remind(record: any, task_scheduler=task_scheduler):
    """
    添加间隔 提醒任务
    重复-10-提醒内容
    """
    text = record.content
    result = text.split('-')
    if len(result) == 3:
        seconds = int(result[1])
        tips = result[2]
        trigger = IntervalTrigger(seconds=seconds)
        task_scheduler.add_job_interval(
            task_scheduler.send_remind, trigger, [tips, record.roomid])
        log.info(f'添加重复提醒任务: 每隔{seconds}秒, 提醒内容: {tips}')
