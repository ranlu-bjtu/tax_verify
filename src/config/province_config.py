"""Province-based tax bureau routing configuration.

Mirrors the EtaxPlugin's province→URL/port/cookie mappings exactly.
Each province has a specific:
  - etax main site URL (with province-specific port)
  - tpass login URL (always :8443)
  - loginb page URL
  - tpass cookie key for login session detection
  - tax domains that need cookies set
"""

# ── Port calculation (from EtaxPlugin utils/index.js) ──────────────────────

# Provinces that use default port 443 (no explicit port in URL)
NO_PORT_PROVINCES = {"shaanxi", "sichuan"}

# Province with special port
SPECIAL_PORTS = {"xizang": 5100}

# Default port for all other provinces
DEFAULT_PORT = 8443


def calc_etax_port(province: str) -> str:
    """Calculate port suffix for etax/tpass URLs based on province.

    Returns:
        ':5100' for xizang
        '' (empty) for shaanxi, sichuan  (default port 443)
        ':8443' for all other provinces
    """
    if province in SPECIAL_PORTS:
        return f":{SPECIAL_PORTS[province]}"
    if province in NO_PORT_PROVINCES:
        return ""
    return f":{DEFAULT_PORT}"


# ── Province → tpass cookie key (from cont-insert-cookie-tpass-login.js) ──

TPASS_COOKIE_KEY_MAP = {
    "tianjin": "tpass_mb29dc78543X4X769Hd7d8a35Hdd5236",
    "shanghai": "tpass_ze998d5f7k8646c2af8c7k878e5ze7fd",
    "shandong": "tpass_p34t7f7cf9pf434t848t588ft6bppbc8",
    "guangdong": "tpass_ssdbs2iqe46q4fs6bc5cbif27ibe8ieb",
    "chongqing": "tpass_sb2cb3a752324a5aaf78aeb5f5ebssac",
    "hunan": "tpass_x774e745d5k24ex5a7kkk375x933f654",
    "hebei": "tpass_y27ew29w8w424ywyy9383dw8d7wy3b3y",
    "beijing": "tpass_jcdjcb7ezjc84dz7az5fz4bb23cc3zc9",
    "zhejiang": "tpass_p3d8j63p8b6p4bbab8dca4832a7fj9cc",
    "shanxi": "tpass_yb8ee73y2ehh445a9bhb39cf473e585a",
    "neimenggu": "tpass_bx74f66a87d64bdf8ff8b7b9a4dfx375",
    "fujian": "tpass_y29fd969ada44b9fb2y9et5567ed262t",
    "yunnan": "tpass_m7d4a8meca944da79ppdb4bef7d7795a",
    "shaanxi": "tpass_rp6c795892e246589rce27cb67dbec54",
    "jiangxi": "tpass_e62p7bde6272429sp56pps44ppceps9p",
    "hubei": "tpass_n6s4de5cb89s4cf28997482cfnb7s4en",
    "henan": "tpass_s84ad3c7cecc4acdbcdc5e87cb37c7sc",
    "dalian": "tpass_u9d4m93ueae24u8e8cc756u6b78d29ae",
    "jiangsu": "tpass_k238ck9eedkb48a9a5d7k5c2c5kkka58",
    "guangxi": "tpass_r36cb7e87rec486b9ffb5874br9eba2a",
    "heilongjiang": "tpass_sse3d26fp9x94cxebc7c4674sdx25cef",
    "xizang": "tpass_sfaf98eabaf84s7baaf75f5f4a5seffe",
    "jilin": "tpass_g6x9dxdrx94847xr9556584ab65rg5bb",
    "xinjiang": "tpass_ec95c8cwa7ef49ewad282efewe4229ea",
    "liaoning": "tpass_x7v6v686a2f44x99axaa44b2a72a6bea",
    "hainan": "tpass_c84fc6b277aa476c92c2cc6cancbbf2c",
    "sichuan": "tpass_dr55crbcrrr64rrdbre3brd53rrrfr24",
    "xiamen": "tpass_udu889aab99b48f98cdccb36eeub995d",
    "anhui": "tpass_vw5vafc9w7dd4e9e9w8d5vbc66889d55",
    "qinghai": "tpass_acdc8d4qeq5c438eaac82q946454369q",
    "ningxia": "tpass_s6cansa64s4743es8f6s724d8499954n",
    "ningbo": "tpass_u9c8bu9f267w43b39jc33382wf3acj39",
    "guizhou": "tpass_xjmd5madc5944md9834j4xxcf2j54cm8",
    "shenzhen": "tpass_kc98bk95c58k46g4adfbg5bkb5fd3659",
    "gansu": "tpass_p9bgggp42aa744wabgg5ggg2367g2g96",
    "qingdao": "tpass_f5d843e943fd4f7692ff953f35f7fccd",
}


def get_tpass_cookie_key(province: str) -> str:
    """Get the province-specific tpass cookie key name."""
    return TPASS_COOKIE_KEY_MAP.get(province, "")


# ── Province URL construction (from inject-bridge-login.js) ────────────────

def get_loginb_url(province: str) -> str:
    """Build the loginb page URL for a province.

    Example: shandong → https://etax.shandong.chinatax.gov.cn:8443/loginb/
             shaanxi  → https://etax.shaanxi.chinatax.gov.cn/loginb/
             xizang   → https://etax.xizang.chinatax.gov.cn:5100/loginb/
    """
    port = calc_etax_port(province)
    return f"https://etax.{province}.chinatax.gov.cn{port}/loginb/"


def get_tpass_login_url(province: str, redirect_uri: str = "",
                        client_id: str = "", cookie: str = "") -> str:
    """Build the tpass login URL with cookie parameter.

    Mirrors: `https://tpass.${province}.chinatax.gov.cn:8443/#/login?...&cookie=${loginCookies}`
    Note: tpass always uses :8443 regardless of province (per EtaxPlugin code).
    """
    import urllib.parse
    url = f"https://tpass.{province}.chinatax.gov.cn:8443/#/login"
    params = []
    if redirect_uri:
        params.append(f"redirect_uri={urllib.parse.quote(redirect_uri)}")
    if client_id:
        params.append(f"client_id={client_id}")
    if cookie:
        params.append(f"cookie={urllib.parse.quote(cookie)}")
    if params:
        url += "?" + "&".join(params)
    return url


def get_tax_domains(province: str) -> list[str]:
    """Build the list of tax bureau cookie domains for a province.

    Mirrors the taxDomains array in inject-bridge-login.js userLogin().
    """
    port = calc_etax_port(province)
    return [
        "https://www.chinatax.gov.cn/",
        "https://chinatax.gov.cn/",
        f"https://{province}.chinatax.gov.cn/",
        f"https://tpass.{province}.chinatax.gov.cn/",
        f"https://tpass.{province}.chinatax.gov.cn{port}/",
        f"https://dppt.{province}.chinatax.gov.cn{port}/",
        f"https://etax.{province}.chinatax.gov.cn/",
        f"https://etax.{province}.chinatax.gov.cn/dwsbf-app-ww-web",
        f"https://www.etax.{province}.chinatax.gov.cn/",
        f"https://etax.{province}.chinatax.gov.cn{port}/",
        f"https://etax-xwcj.{province}.chinatax.gov.cn/",
        f"https://znhd.{province}.chinatax.gov.cn/",
        f"https://znhd.{province}.chinatax.gov.cn{port}/",
    ]