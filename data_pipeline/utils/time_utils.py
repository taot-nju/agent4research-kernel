from datetime import datetime, timezone, timedelta


BEIJING_TZ = timezone(timedelta(hours=8))


def now_beijing_iso():
    """
    返回带时区的北京时间 ISO 字符串。
    例如：2026-06-04T17:30:00+08:00
    """
    return datetime.now(BEIJING_TZ).isoformat(timespec="seconds")

if __name__ == '__main__':
    print(now_beijing_iso())