"""cn_tech/ — 中文技术社区域（v1）

Sources: csdn / juejin / linuxdo / nodeseek / hostloc / v2ex / coolapk / xiaohongshu
Compat(deprecated): community_cn
"""

from souwen.web.csdn import CSDNClient
from souwen.web.juejin import JuejinClient
from souwen.web.linuxdo import LinuxDoClient
from souwen.web.nodeseek import NodeSeekClient
from souwen.web.hostloc import HostLocClient
from souwen.web.v2ex import V2EXClient
from souwen.web.coolapk import CoolapkClient
from souwen.web.xiaohongshu import XiaohongshuClient
from souwen.web.community_cn import CommunityCnClient

__all__ = [
    "CSDNClient",
    "JuejinClient",
    "LinuxDoClient",
    "NodeSeekClient",
    "HostLocClient",
    "V2EXClient",
    "CoolapkClient",
    "XiaohongshuClient",
    "CommunityCnClient",
]
