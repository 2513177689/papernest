import ipaddress
import socket
from urllib.parse import urlparse
from cryptography.fernet import Fernet
from . import db

OFFICIAL_HOSTS={'api.deepseek.com','api.moonshot.cn','api.moonshot.ai','api.openai.com',
    'api.anthropic.com','generativelanguage.googleapis.com','dashscope.aliyuncs.com',
    'dashscope-intl.aliyuncs.com','dashscope-us.aliyuncs.com','ark.cn-beijing.volces.com',
    'open.bigmodel.cn','api.minimax.cn','api.minimax.io','api.minimaxi.com','arxiv.org',
    'export.arxiv.org','api.openalex.org','api.crossref.org'}


def proxy_address(address):
    """Known fake-IP ranges used by local DNS proxy clients, not private LAN ranges."""
    ip=ipaddress.ip_address(address)
    return ip in ipaddress.ip_network('198.18.0.0/15') if ip.version==4 else ip in ipaddress.ip_network('fdfe:dcba:9876::/48')


def cipher():
    path = db.DATA / '.secret.key'
    if not path.exists():
        try:
            with path.open('xb') as f:
                f.write(Fernet.generate_key())
            path.chmod(0o600)
        except FileExistsError:
            pass
    return Fernet(path.read_bytes())


def encrypt(value):
    return cipher().encrypt(value.encode()).decode() if value else ''


def decrypt(value):
    return cipher().decrypt(value.encode()).decode() if value else ''


def public_url(url, allow_local=False):
    u = urlparse(url)
    if u.scheme not in {'https','http'} or not u.hostname or u.username or u.password:
        raise ValueError('请输入有效的 HTTP(S) 地址，不要在地址中包含密钥。')
    if u.query and ('key=' in u.query.lower() or 'token=' in u.query.lower()):
        raise ValueError('请将密钥填入专用字段。')
    if allow_local and u.hostname in {'127.0.0.1','localhost','::1'}:
        return url
    if u.scheme != 'https':
        raise ValueError('外部服务必须使用 HTTPS。')
    try:
        addresses = socket.getaddrinfo(u.hostname, u.port or 443, type=socket.SOCK_STREAM)
    except socket.gaierror as e:
        raise ValueError('无法解析该地址，请检查网络或域名。') from e
    if any(not ipaddress.ip_address(a[4][0]).is_global and not
           (u.hostname in OFFICIAL_HOSTS and proxy_address(a[4][0])) for a in addresses):
        raise ValueError('不能获取内网地址。')
    return url
