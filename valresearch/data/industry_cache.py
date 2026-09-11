# -*- coding: utf-8 -*-
"""行业数据缓存管理。

功能：
1. 优先从本地数据库(vr_stocks)获取行业数据
2. 如果本地没有，从远程API获取(Sina/东方财富)
3. 获取后缓存到本地数据库，供后续使用

数据源优先级：
1. 本地vr_stocks缓存
2. Sina行业分类API
3. 东方财富API
4. 关键词推断（兜底）
"""
import time
import re
import requests
import pandas as pd

# 全局缓存
_industry_cache = {}
_cache_loaded = False


def _load_cache():
    """从本地数据库加载行业缓存。"""
    global _industry_cache, _cache_loaded
    if _cache_loaded:
        return
    try:
        import stock_db as db
        conn = db.connect()
        ind_map = db.get_industry_map(conn)
        conn.close()
        if ind_map:
            _industry_cache.update(ind_map)
    except Exception:
        pass
    _cache_loaded = True


def _save_to_db(industry_map):
    """保存行业数据到本地数据库。"""
    try:
        import stock_db as db
        conn = db.connect()
        rows = [(code, '', industry, '', '', '') for code, industry in industry_map.items()]
        db.save_vr_stocks(conn, rows)
        conn.close()
    except Exception:
        pass


def _normalize_industry(industry):
    """标准化行业名称，保持与Excel文件一致。"""
    if not industry:
        return ''
    
    # 行业名称映射（Sina/东方财富 -> 标准名称）
    industry_map = {
        '金融行业': '银行',
        '银行Ⅱ': '银行',
        '银行Ⅲ': '银行',
        '饮料乳品': '食品行业',
        '食品加工': '食品行业',
        '食品饮料': '食品行业',
        '白色家电': '家电行业',
        '小家电': '家电行业',
        '大家电': '家电行业',
        '照明设备': '家电行业',
        '家居用品': '家电行业',
        '家具制造': '家电行业',
        '纺织服饰': '纺织行业',
        '服装家纺': '纺织行业',
        '医疗器械': '生物制药',
        '化学制药': '生物制药',
        '中药': '生物制药',
        '生物制品': '生物制药',
        '汽车零部件': '汽车制造',
        '乘用车': '汽车制造',
        '商用车': '汽车制造',
        '水泥建材': '建筑建材',
        '玻璃建材': '建筑建材',
        '陶瓷建材': '建筑建材',
        '化学原料': '化工行业',
        '化学制品': '化工行业',
        '专用设备': '机械行业',
        '通用设备': '机械行业',
        '仪器仪表': '机械行业',
        '轨道交通设备': '机械行业',
        '物流': '交通运输',
        '航空运输': '交通运输',
        '公路铁路运输': '交通运输',
        '港口航运': '交通运输',
        '电力': '电力行业',
        '燃气': '电力行业',
        '供水': '供水供气',
        '商业百货': '商业百货',
        '零售': '商业百货',
        '消费电子': '电子信息',
        '计算机设备': '电子信息',
        '软件开发': '电子信息',
        'IT服务': '电子信息',
        '环保工程': '环保行业',
        '环境治理': '环保行业',
        '房地产开发': '房地产',
        '房地产服务': '房地产',
        '煤炭开采': '煤炭行业',
        '煤炭加工': '煤炭行业',
        '钢铁': '钢铁行业',
        '有色金属': '有色金属',
        '造纸': '造纸行业',
        '包装印刷': '印刷包装',
    }
    
    # 检查是否有精确匹配
    if industry in industry_map:
        return industry_map[industry]
    
    # 检查是否包含关键词
    for key, value in industry_map.items():
        if key in industry:
            return value
    
    return industry


def _fetch_from_sina():
    """从Sina获取行业分类数据。"""
    industry_map = {}
    try:
        # 获取行业列表
        url = 'https://vip.stock.finance.sina.com.cn/q/view/newSinaHy.php'
        headers = {'Referer': 'https://finance.sina.com.cn'}
        r = requests.get(url, headers=headers, timeout=10)
        
        text = r.text
        match = re.search(r'=\s*(\{.*\})', text, re.DOTALL)
        if not match:
            return industry_map
        
        json_str = match.group(1)
        industries = {}
        for item in re.finditer(r'"(\w+)":"(\w+),([^"]+)"', json_str):
            code = item.group(2)
            name = item.group(3).split(',')[0]
            industries[code] = name
        
        # 获取每个行业的股票
        for industry_code, industry_name in industries.items():
            page = 1
            while True:
                url = 'https://vip.stock.finance.sina.com.cn/quotes_service/api/json_v2.php/Market_Center.getHQNodeData'
                params = {
                    'page': page,
                    'num': 100,
                    'sort': 'symbol',
                    'asc': 1,
                    'node': industry_code,
                    '_s_r_a': 'page'
                }
                headers = {'Referer': 'https://finance.sina.com.cn'}
                
                try:
                    r = requests.get(url, params=params, headers=headers, timeout=10)
                    if r.status_code == 200:
                        text = r.text
                        codes = re.findall(r'"symbol":"(\w+)"', text)
                        if not codes:
                            break
                        for code in codes:
                            if code.startswith('sh') or code.startswith('sz'):
                                code = code[2:]
                            industry_map[code] = _normalize_industry(industry_name)
                        page += 1
                        time.sleep(0.2)
                    else:
                        break
                except Exception:
                    break
    except Exception:
        pass
    return industry_map


def _fetch_from_eastmoney_batch():
    """从东方财富批量API获取行业数据。"""
    industry_map = {}
    try:
        for page in range(1, 100):
            url = 'https://push2.eastmoney.com/api/qt/clist/get'
            params = {
                'pn': page,
                'pz': 100,
                'po': 1,
                'np': 1,
                'ut': 'bd1d9ddb04089700cf9c27f6f7426281',
                'fltt': 2,
                'invt': 2,
                'fid': 'f3',
                'fs': 'm:0+t:6,m:0+t:80,m:1+t:2,m:1+t:23',
                'fields': 'f12,f14,f100'
            }
            headers = {'User-Agent': 'Mozilla/5.0'}
            
            r = requests.get(url, params=params, headers=headers, timeout=10)
            if r.status_code == 200:
                data = r.json()
                if data.get('data') and data['data'].get('diff'):
                    items = data['data']['diff']
                    if not items:
                        break
                    for item in items:
                        code = item.get('f12', '')
                        industry = item.get('f100', '')
                        if code and industry:
                            industry_map[code] = _normalize_industry(industry)
                    time.sleep(0.2)
                else:
                    break
            else:
                break
    except Exception:
        pass
    return industry_map


def _infer_industry_from_name(name):
    """从股票名称推断行业（兜底方案）。"""
    name = str(name)
    
    # 银行
    bank_keywords = ('银行', '金租', '招商银行', '工商银行', '建设银行', '农业银行', '中国银行', 
                    '交通银行', '邮储银行', '浦发银行', '民生银行', '中信银行', '光大银行', 
                    '华夏银行', '平安银行', '北京银行', '江苏银行', '上海银行', '宁波银行', 
                    '南京银行', '杭州银行', '成都银行', '长沙银行', '郑州银行', '西安银行', 
                    '青岛银行', '苏州银行', '重庆银行', '厦门银行', '兴业银行', '广发银行', 
                    '渤海银行', '恒丰银行', '浙商银行')
    if any(k in name for k in bank_keywords):
        return '银行'
    
    # 保险
    insur_keywords = ('保险', '人寿', '新华保险', '中国太保', '中国人保')
    if any(k in name for k in insur_keywords):
        return '保险'
    
    # 证券
    sec_keywords = ('证券', '券商', '中信证券', '国泰君安', '海通证券', '华泰证券')
    if any(k in name for k in sec_keywords):
        return '证券'
    
    # 房地产
    real_keywords = ('地产', '房产', '置业', '家居', '家具', '装饰', '建材', '万科', '保利',
                    '招商蛇口', '金地', '华侨城', '新城', '华夏幸福', '碧桂园', '恒大',
                    '融创', '龙湖', '绿城', '富力', '远洋', '中国奥园', '雅居乐')
    if any(k in name for k in real_keywords):
        return '房地产'
    
    # 食品饮料
    food_keywords = ('食品', '味', '酒', '奶', '乳', '饮料', '面包', '餐饮', '米', '油', '盐', '糖', '茶',
                    '茅台', '五粮液', '泸州老窖', '汾酒', '洋河', '伊利', '蒙牛', '光明', '双汇', '海天',
                    '中粮', '三元', '完达山', '娃哈哈', '农夫山泉', '元气森林')
    if any(k in name for k in food_keywords):
        return '食品行业'
    
    # 酿酒
    wine_keywords = ('酒', '茅台', '五粮液', '泸州老窖', '汾酒', '洋河', '古井贡', '口子窖', '老白干',
                    '舍得', '酒鬼', '水井坊', '金徽酒', '今世缘')
    if any(k in name for k in wine_keywords):
        return '酿酒行业'
    
    # 家电
    home_keywords = ('电器', '家电', '照明', '灯', '空调', '冰箱', '洗衣机', '美的', '格力', '海尔',
                    'TCL', '海信', '创维', '长虹', '康佳', '小熊', '苏泊尔', '九阳')
    if any(k in name for k in home_keywords):
        return '家电行业'
    
    # 纺织服装
    textile_keywords = ('纺织', '服装', '鞋', '衣', '家纺', '袜', '帽', '安踏', '李宁', '特步',
                    '361度', '鸿星尔克', '森马', '美特斯邦威', '海澜之家', '太平鸟')
    if any(k in name for k in textile_keywords):
        return '纺织行业'
    
    # 医药
    medical_keywords = ('药', '医', '生物', '健康', '制药', '恒瑞', '药明康德', '迈瑞医疗',
                    '爱尔眼科', '通策医疗', '片仔癀', '云南白药', '同仁堂', '东阿阿胶')
    if any(k in name for k in medical_keywords):
        return '生物制药'
    
    # 汽车
    auto_keywords = ('汽车', '车', '轮胎', '比亚迪', '长城汽车', '吉利', '长安', '上汽', '广汽',
                    '一汽', '北汽', '奇瑞', '江淮', '力帆', '众泰', '东风')
    if any(k in name for k in auto_keywords):
        return '汽车制造'
    
    # 建筑建材
    construction_keywords = ('建筑', '建材', '水泥', '混凝土', '工程', '设计院', '中国建筑',
                    '中国中铁', '中国铁建', '中国交建', '中国电建', '海螺水泥', '华新水泥')
    if any(k in name for k in construction_keywords):
        return '建筑建材'
    
    # 化工
    chemical_keywords = ('化工', '化学', '材料', '树脂', '涂料', '万华化学', '恒力石化',
                    '荣盛石化', '桐昆股份', '卫星石化', '新和成', '龙蟒佰利')
    if any(k in name for k in chemical_keywords):
        return '化工行业'
    
    # 机械
    machinery_keywords = ('机械', '设备', '仪器', '仪表', '数控', '泵', '三一重工', '中联重科',
                    '徐工机械', '柳工', '安徽合力', '杭叉集团', '艾迪精密')
    if any(k in name for k in machinery_keywords):
        return '机械行业'
    
    # 交通运输
    transport_keywords = ('物流', '运输', '港口', '航运', '快递', '铁路', '公路', '大桥',
                    '中远海控', '招商轮船', '中国外运', '顺丰', '中通', '韵达', '圆通', '申通')
    if any(k in name for k in transport_keywords):
        return '交通运输'
    
    # 煤炭（放在电力能源之前，因为煤炭更具体）
    coal_keywords = ('煤', '神华', '中煤', '兖矿', '陕西煤业', '淮北矿业', '平煤', '潞安',
                    '阳泉', '大同', '晋煤', '焦煤')
    if any(k in name for k in coal_keywords):
        return '煤炭行业'
    
    # 电力能源
    energy_keywords = ('能源', '燃气', '电力', '电气', '天然气', '风电', '光伏',
                    '中煤能源', '中国石油', '中国石化', '中海油', '长江电力', '华能国际',
                    '国电电力', '大唐发电')
    if any(k in name for k in energy_keywords):
        return '电力行业'
    
    # 保险
    insur_keywords = ('保险', '人寿', '平安', '新华保险', '中国太保', '中国人保')
    if any(k in name for k in insur_keywords):
        return '保险'
    
    # 商业零售
    retail_keywords = ('百货', '商业', '零售', '黄金', '珠宝', '中国中免', '王府井', '重庆百货',
                    '天虹股份', '永辉超市', '家家悦', '红旗连锁', '步步高')
    if any(k in name for k in retail_keywords):
        return '商业百货'
    
    # 科技电子
    tech_keywords = ('科技', '电子', '软件', '信息', '网络', '通信', '智能', '华为', '中兴',
                    '海康威视', '大华股份', '歌尔股份', '立讯精密', '京东方', 'TCL科技',
                    '用友网络', '金山办公', '科大讯飞', '中芯国际', '韦尔股份')
    if any(k in name for k in tech_keywords):
        return '电子信息'
    
    # 环保
    env_keywords = ('环保', '环境', '污水', '垃圾', '碧水源', '首创环保', '瀚蓝环境')
    if any(k in name for k in env_keywords):
        return '环保行业'
    
    # 农业
    agri_keywords = ('农', '种', '牧', '渔', '林', '牧原股份', '温氏股份', '新希望',
                    '正邦科技', '天邦食品', '傲农生物', '大北农', '海大集团', '新希望')
    if any(k in name for k in agri_keywords):
        return '农林牧渔'
    
    # 传媒
    media_keywords = ('传媒', '文化', '出版', '影视', '游戏', '芒果超媒', '光线传媒',
                    '华策影视', '中国电影', '万达电影', '分众传媒')
    if any(k in name for k in media_keywords):
        return '传媒娱乐'
    
    # 钢铁
    steel_keywords = ('钢铁', '钢', '铁', '宝钢', '鞍钢', '河钢', '沙钢', '建龙', '首钢')
    if any(k in name for k in steel_keywords):
        return '钢铁行业'
    
    # 有色金属
    metal_keywords = ('有色', '铜', '铝', '锌', '黄金', '银', '稀土', '锂', '紫金矿业',
                    '北方稀土', '赣锋锂业', '天齐锂业', '华友钴业', '洛阳钼业')
    if any(k in name for k in metal_keywords):
        return '有色金属'
    
    return ''


def get_industry(code, name=''):
    """获取股票行业信息。
    
    优先级：本地缓存 -> 关键词推断（无网络） -> 远程API（仅兜底）
    
    Args:
        code: 股票代码(6位)
        name: 股票名称(可选，用于关键词推断)
    
    Returns:
        行业名称字符串，未找到返回空字符串
    """
    global _industry_cache, _cache_loaded
    
    # 加载本地缓存
    _load_cache()
    
    code = str(code).zfill(6)
    
    # 1. 检查本地缓存
    if code in _industry_cache and _industry_cache[code]:
        return _industry_cache[code]
    
    # 2. 关键词推断（无网络请求，快速）
    if name:
        industry = _infer_industry_from_name(name)
        if industry:
            _industry_cache[code] = industry
            _save_to_db({code: industry})
            return industry
    
    # 3. 远程API（仅兜底）
    try:
        # 东方财富批量API
        em_map = _fetch_from_eastmoney_batch()
        if code in em_map:
            _industry_cache[code] = em_map[code]
            _save_to_db({code: em_map[code]})
            return em_map[code]
    except Exception:
        pass
    
    return ''


def batch_get_industries(codes_with_names):
    """批量获取行业信息。
    
    优化策略：本地缓存 -> 关键词推断（无网络） -> 远程API（仅兜底）
    
    Args:
        codes_with_names: [(code, name), ...] 股票代码和名称列表
    
    Returns:
        {code: industry} 字典
    """
    global _industry_cache, _cache_loaded
    
    # 加载本地缓存
    _load_cache()
    
    result = {}
    missing = []
    
    # 1. 先从本地缓存获取
    for code, name in codes_with_names:
        code = str(code).zfill(6)
        if code in _industry_cache and _industry_cache[code]:
            result[code] = _industry_cache[code]
        else:
            missing.append((code, name))
    
    if not missing:
        return result
    
    # 2. 关键词推断（无网络请求，快速）
    still_missing = []
    for code, name in missing:
        industry = _infer_industry_from_name(name)
        if industry:
            result[code] = industry
            _industry_cache[code] = industry
        else:
            still_missing.append((code, name))
    
    if not still_missing:
        # 保存推断结果到数据库
        _save_to_db({c: result[c] for c in result})
        return result
    
    # 3. 远程API（仅兜底，且仅对无法推断的少量股票）
    try:
        # 东方财富批量API（比Sina快）
        em_map = _fetch_from_eastmoney_batch()
        for code, name in still_missing:
            if code in em_map:
                result[code] = em_map[code]
                _industry_cache[code] = em_map[code]
    except Exception:
        pass
    
    # 保存到数据库
    _save_to_db({c: result[c] for c in result if c in [m[0] for m in missing]})
    
    return result


def get_all_industries():
    """获取所有已缓存的行业数据。"""
    _load_cache()
    return dict(_industry_cache)


if __name__ == '__main__':
    # 测试
    test_codes = [
        ('600036', '招商银行'),
        ('000858', '五粮液'),
        ('002714', '牧原股份'),
        ('601398', '工商银行'),
        ('000001', '平安银行'),
    ]
    
    for code, name in test_codes:
        industry = get_industry(code, name)
        print(f'{code} {name}: {industry}')
