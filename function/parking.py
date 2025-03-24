import mysql.connector
from mysql.connector import Error
import time
import re
from sendqueue import QueueDB
from config.config import Config

config = Config()
park_admin = config.get_config('park_admin')[0]


def send_remind(tips, receiver, produce='parking'):
    mid = str(time.time().__int__())
    with QueueDB() as q:
        q.send_text(mid, tips, receiver, '', produce)
    time.sleep(1)


async def get_parking_records(record):
    r = re.match(r'车辆进出查询(\d*)', record.content)
    try:
        cnts = int(r.group(1))
    except:
        cnts = 10
    print(cnts)
    try:
        # 从配置文件获取数据库连接信息
        db_config = config.get_config('park_db')
        # 建立数据库连接
        connection = mysql.connector.connect(**db_config)

        if connection.is_connected():
            cursor = connection.cursor()

            # 查询最新的10条记录，并格式化InOutTime
            query = """
                SELECT 
                    InOutTime,
                    Plate, 
                    UserName, 
                    IOType
                FROM inoutrecord 
                ORDER BY InOutTime DESC 
                LIMIT %s
            """
            cursor.execute(query, (cnts,))

            # 获取查询结果
            records = cursor.fetchall()
            tips = f"最新{cnts}条记录:"
            for record in sorted(records, key=lambda x: x[0], reverse=True):
                tips += f"\n时间: {record[0]}, 车牌: {record[1]}, 用户: {record[2]}, 类型: {record[3]}"
            send_remind(tips, park_admin, 'parking')

    except Error as e:
        send_remind(f"连接数据库时出错: {e}", park_admin, 'parking')

    finally:
        if 'connection' in locals() and connection.is_connected():
            cursor.close()
            connection.close()

record_list = []


async def watching_parking():
    # send_remind = print
    global record_list
    try:
        # 从配置文件获取数据库连接信息
        db_config = config.get_config('park_db')
        # 建立数据库连接
        connection = mysql.connector.connect(**db_config)

        if connection.is_connected():
            cursor = connection.cursor()

            # 查询最新的10条记录，并格式化InOutTime
            query = """
                SELECT 
                    InOutTime,
                    Plate, 
                    UserName, 
                    IOType
                FROM inoutrecord 
                ORDER BY InOutTime DESC 
                LIMIT 1
            """
            cursor.execute(query)

            # 获取查询结果
            record = cursor.fetchone()
            tips = f"车辆"
            record_time = record_list[-1] if record_list else ''
            if record_time == record[0]:
                # send_remind(tips, park_admin, 'parking')
                return
            else:
                record_list.append(record[0])
                tips += f"{record[3]}:"
                tips += f"\n{record[0]} {record[2]} {record[1]}"
                send_remind(tips, park_admin, 'parking')
                return

    except Error as e:
        send_remind(f"连接数据库时出错: {e}", park_admin, 'parking')

    finally:
        if 'connection' in locals() and connection.is_connected():
            cursor.close()
            connection.close()
