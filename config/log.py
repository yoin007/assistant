# _*_ coding: utf-8 _*_

import os
import logging
import logging.config

class LogConfig:
    def __init__(self, module_name='bot'):
        self.log_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'logs')
        self.log_name = module_name
        self.__config_logging()

    def __config_logging(self):
        """配置日志"""
        if not os.path.exists(self.log_path):
            os.makedirs(self.log_path)

        logging_config = {
            'version': 1,
            'disable_existing_loggers': False,
            'formatters': {
                'default': {
                    'format': '%(asctime)s - %(name)s - %(levelname)s - %(funcName)s - %(message)s'
                },
            },
            'handlers': {
                'console_handler': {
                    'class': 'logging.StreamHandler',
                    'formatter': 'default',
                    'stream': 'ext://sys.stdout'
                },
                'info_file_handler': {
                    'class': 'logging.FileHandler',
                    'formatter': 'default',
                    'filename': os.path.join(self.log_path, f'{self.log_name}.log'),
                    'encoding': 'utf-8',
                    'mode': 'a'
                },
                'error_file_handler': {
                    'class': 'logging.FileHandler',
                    'level': 'ERROR',
                    'formatter': 'default',
                    'filename': os.path.join(self.log_path, f'{self.log_name}_error.log'),
                    'encoding': 'utf-8',
                    'mode': 'a'
                }
            },
            'loggers': {
                '': {
                    'handlers': ['console_handler', 'info_file_handler', 'error_file_handler'],
                    'level': 'INFO',
                }
            }
        }
        logging.config.dictConfig(logging_config)
        logging.getLogger('watchfiles.main').setLevel(logging.ERROR)
        logging.getLogger('apscheduler.executors.default').setLevel(logging.WARNING)
        

    def get_logger(self):
        return logging.getLogger(self.log_name)

# 使用方法
# logger = LogConfig(__name__).get_logger()
# logger.info("This is an info message")
# logger.error("This is an error message")