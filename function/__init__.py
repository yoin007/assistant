# _*_ coding: utf-8 _*_
# @Time: 2024/09/24 22:31
# @Author: Tech_T


from function.manage.member import insert_member, del_member, start_func, stop_func, wxid_name_remark, query_permission, insert_permission
from function.manage.manage import hi_to_new_friend, invite_chatroom_member, auto_new_friend
from function.api import weather_report, zhipu_answer, zhipu_video, zhaosheng_assistant
from function.lesson.lesson import update_schedule, teacher_schedule, get_current_schedule, get_ip_info, mass_message, update_schedule_all, get_current_teacher, get_today_schedule, today_teachers, current_week_info, guide_template
from function.lesson.notes import insert_note, get_notes
from function.lesson.homework import incert_homework, get_class_homework, incert_announcement
from function.parking import get_parking_records
from function.task import get_task_list, stop_task_job, add_cron_remind
