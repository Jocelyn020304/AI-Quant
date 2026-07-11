"""
股票数据 API 后端 — 提供股票行情数据查询接口
启动: cd "Task 2" && python backend.py
"""
import json
import time
import urllib.request
import urllib.parse
from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs

# ---------- 配置 ----------
HOST = '127.0.0.1'
PORT = 8080

# ---------- 股票代码映射 ----------
def code_to_secid(code):
    """将股票代码转换为东方财富 secid 格式"""
    code = code.strip().upper()
    # 移除可能的后缀 .SH / .SZ
    suffix = ''
    if code.endswith('.SH'):
        code = code[:-3]
        suffix = 'SH'
    elif code.endswith('.SZ'):
        code = code[:-3]
        suffix = 'SZ'
    
    # 数字部分
    num = ''.join(filter(str.isdigit, code))
    if not num:
        return None
    
    # 判断市场
    if suffix:
        market = '1' if suffix == 'SH' else '0'
    elif num.startswith(('6', '9')) or len(num) == 6 and num[0] in ('5', '68', '78', '58'):
        market = '1'  # 上交所
    elif num.startswith(('0', '3')):
        market = '0'  # 深交所
    else:
        market = '1'
    
    return f"{market}.{num}"


def fetch_kline(secid, start_date='', end_date=''):
    """从东方财富 API 获取日 K 线数据"""
    url = (
        f"https://push2his.eastmoney.com/api/qt/stock/kline/get"
        f"?secid={secid}"
        f"&fields1=f1,f2,f3,f4,f5,f6"
        f"&fields2=f51,f52,f53,f54,f55,f56,f57,f58,f59,f60,f61"
        f"&klt=101"          # 日K
        f"&fqt=1"            # 前复权
        f"&beg={start_date}"
        f"&end={end_date}"
        f"&lmt=500"          # 最多500条
    )
    
    req = urllib.request.Request(url, headers={
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
        'Referer': 'https://quote.eastmoney.com/'
    })
    
    with urllib.request.urlopen(req, timeout=10) as resp:
        data = json.loads(resp.read().decode('utf-8'))
    
    if data.get('data') is None or data['data'].get('klines') is None:
        return None
    
    klines = data['data']['klines']
    rows = []
    for line in klines:
        parts = line.split(',')
        if len(parts) >= 11:
            rows.append({
                'trade_date': parts[0],
                'open': float(parts[1]),
                'close': float(parts[2]),
                'high': float(parts[3]),
                'low': float(parts[4]),
                'vol': float(parts[5]),
                'amount': float(parts[6]),
                'change_pct': float(parts[7]) if parts[7] else 0,
                'change': float(parts[8]) if parts[8] else 0,
            })
    
    # 计算 pre_close
    for i in range(len(rows) - 1, 0, -1):
        rows[i]['pre_close'] = rows[i - 1]['close']
    if rows:
        rows[0]['pre_close'] = rows[0]['open']
    
    return rows


def search_stock(keyword):
    """搜索股票代码（返回匹配的股票列表）"""
    encoded = urllib.parse.quote(keyword)
    url = f"https://searchadapter.eastmoney.com/api/suggest/get?input={encoded}&type=14&token=D43BF722C8E33CDC0E8F992A14DED6D2&count=10"
    
    req = urllib.request.Request(url, headers={
        'User-Agent': 'Mozilla/5.0',
        'Referer': 'https://www.eastmoney.com/'
    })
    
    try:
        with urllib.request.urlopen(req, timeout=5) as resp:
            data = json.loads(resp.read().decode('utf-8'))
        if data.get('Data') and data['Data']:
            results = []
            for item in data['Data']:
                code = item.get('Code', '')
                name = item.get('Name', '')
                stype = item.get('Type', '')
                if stype in ('1', '2', '3'):  # 仅股票
                    results.append({
                        'code': code,
                        'name': name,
                        'market': 'SH' if code.startswith(('6', '9')) else 'SZ'
                    })
            return results
    except Exception:
        # 备用搜索接口
        url2 = f"https://suggest3.sinajs.cn/suggest/name={encoded}"
        try:
            req2 = urllib.request.Request(url2, headers={'User-Agent': 'Mozilla/5.0', 'Referer': 'https://finance.sina.com.cn/'})
            with urllib.request.urlopen(req2, timeout=5) as resp2:
                raw = resp2.read().decode('gbk')
                # 解析新浪返回格式
                parts = raw.split(';')
                results = []
                for p in parts:
                    items = p.split(',')
                    if len(items) >= 4 and items[1]:
                        results.append({'code': items[1], 'name': items[3], 'market': 'SH' if items[1].startswith(('6', '9')) else 'SZ'})
                return results
        except Exception:
            return None


# ---------- HTTP 服务 ----------
class StockAPIHandler(BaseHTTPRequestHandler):
    def _send_json(self, data, status=200):
        self.send_response(status)
        self.send_header('Content-Type', 'application/json; charset=utf-8')
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Methods', 'GET, OPTIONS')
        self.send_header('Access-Control-Allow-Headers', 'Content-Type')
        self.end_headers()
        self.wfile.write(json.dumps(data, ensure_ascii=False).encode('utf-8'))
    
    def do_OPTIONS(self):
        self._send_json({})
    
    def do_GET(self):
        parsed = urlparse(self.path)
        params = parse_qs(parsed.query)
        path = parsed.path.rstrip('/')
        
        # 健康检查
        if path == '/api/health':
            return self._send_json({'status': 'ok', 'time': time.strftime('%Y-%m-%d %H:%M:%S')})
        
        # 搜索股票
        if path == '/api/search':
            keyword = (params.get('keyword') or [''])[0]
            if not keyword:
                return self._send_json({'error': '请输入关键词'}, 400)
            results = search_stock(keyword)
            return self._send_json({'data': results or []})
        
        # 获取K线
        if path == '/api/kline':
            code = (params.get('code') or [''])[0]
            start = (params.get('start') or [''])[0]
            end = (params.get('end') or [''])[0]
            
            if not code:
                return self._send_json({'error': '请输入股票代码'}, 400)
            
            secid = code_to_secid(code)
            if not secid:
                return self._send_json({'error': f'无效的股票代码: {code}'}, 400)
            
            rows = fetch_kline(secid, start, end)
            if rows is None or len(rows) == 0:
                return self._send_json({'error': f'未获取到数据，请检查股票代码是否正确'}, 404)
            
            return self._send_json({'data': rows, 'count': len(rows), 'secid': secid})
        
        self._send_json({'error': 'Not Found'}, 404)
    
    def log_message(self, format, *args):
        print(f"[{time.strftime('%H:%M:%S')}] {args[0]} {args[1]} {args[2]}")


def run_server():
    server = HTTPServer((HOST, PORT), StockAPIHandler)
    print(f"股票数据 API 后端已启动")
    print(f"   http://{HOST}:{PORT}/api/health")
    print(f"   http://{HOST}:{PORT}/api/search?keyword=寒武纪")
    print(f"   http://{HOST}:{PORT}/api/kline?code=688256&start=20250601&end=20260630")
    print(f"按 Ctrl+C 停止服务")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n服务已停止")
        server.server_close()

if __name__ == '__main__':
    run_server()
