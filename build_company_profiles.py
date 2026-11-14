"""국내 기업 사업 소개 캐시 만들기 (앱은 결과 파일만 읽어요. 앱 실행 중에는 네트워크를 쓰지 않아요)

입력: fdr.StockListing('KRX-DESC')로 받은 KIND 상장법인목록 CSV (Code, Name, Industry, Products, HomePage …)
     예) python build_company_profiles.py data/raw/krx_desc_20261114.csv 2026-11-14
출력: data/company_profiles_kr.csv — 재무 CSV(data/재무_2026.csv)의 806개 기업 기준으로 종목코드(문자열)로 붙여요.

규칙
- 종목코드가 상장법인목록에 없으면 status=missing, 회사 이름이 다르면(이름 변경 등) status=name_mismatch 로 두고
  소개 문장을 만들지 않아요 (다른 회사 설명을 추정·재사용하지 않아요).
- 소개 문장은 업종(Industry)과 주요 제품(Products) 원문으로 만든 안전한 템플릿이에요. 원문은 products 열에 그대로 남겨요.
- 서비스 핵심 국내 종목(products.csv 개별주 23개)은 원문을 바탕으로 쉬운 말 문장을 직접 적었어요(MANUAL).
- KIND 원문이 오래된 사업을 담고 있는 회사는 회사 공식 최신 자료로 문장·태그·출처를 덮어써요(OFFICIAL).
  이때도 KIND 업종·주요 제품 원문은 industry/products 열에 그대로 남겨요. 다시 만들어도 OFFICIAL 이 유지돼요.
"""
import re
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent
OUT = ROOT / 'data' / 'company_profiles_kr.csv'
SOURCE = 'KIND 상장법인목록 (한국거래소)'
SOURCE_URL = 'https://kind.krx.co.kr/corpgeneral/corpList.do?method=loadInitPage'

# 핵심 국내 23종목: KIND 업종·주요 제품 원문을 초보자용으로 풀어 쓴 문장과 태그
MANUAL = {
    '005930': ('스마트폰·TV 같은 전자제품과 메모리 반도체, 디스플레이를 만드는 회사예요.', ['스마트폰·통신장비', '메모리 반도체', '디스플레이']),
    '000660': ('컴퓨터·서버·스마트폰에 들어가는 반도체를 만드는 회사예요. 메모리 반도체가 주력이에요.', ['반도체', '메모리']),
    '005380': ('승용차·버스·트럭 같은 자동차와 자동차 부품을 만드는 회사예요.', ['승용차', '버스·트럭', '자동차 부품']),
    '035420': ('검색 포털을 운영하고 온라인 광고로 돈을 버는 인터넷 회사예요.', ['포털 서비스', '온라인 광고']),
    '028260': ('무역(상사)·건설·패션 등 여러 사업을 함께 하는 회사예요.', ['상사(도소매)', '건설', '패션']),
    '017670': ('휴대전화 통신 서비스를 제공하는 이동통신 회사예요.', ['이동전화', '부가통신 서비스']),
    '033780': ('담배와 홍삼 제품을 만들어 파는 회사예요.', ['담배', '홍삼 제품']),
    '009150': ('스마트폰·자동차 등 전자기기에 들어가는 부품을 만드는 회사예요.', ['MLCC(적층세라믹콘덴서)', '카메라 모듈', '반도체 패키지 기판']),
    '402340': ('다른 회사들의 지분을 갖고 사업을 관리하는 지주회사예요.', ['지주회사']),
    '006400': ('전기차·전자기기에 쓰이는 2차전지(충전식 배터리)와 전자재료를 만드는 회사예요.', ['2차전지', '전자재료']),
    '028050': ('공장·플랜트 같은 산업 설비를 설계하고 짓는 엔지니어링 회사예요.', ['산업설비 설계', '시공', '공사감리']),
    '353200': ('전자기기의 부품을 연결하는 인쇄회로기판(PCB)을 만드는 회사예요.', ['PCB(인쇄회로기판)']),
    '373220': ('전기차·에너지저장장치(ESS)·소형기기에 쓰이는 2차전지를 만드는 회사예요.', ['자동차 전지', 'ESS', '소형 전지']),
    '105560': ('은행 등 금융회사들을 거느린 금융지주회사예요.', ['금융지주']),
    '012450': ('항공기 엔진과 방산 장비를 만들고 정비하는 회사예요.', ['항공기 엔진', '방산 장비']),
    '042660': ('배를 만드는 조선 회사예요.', ['선박']),
    '068270': ('바이오 의약품을 개발해 만드는 회사예요.', ['램시마', '트룩시마', '허쥬마']),
    '034730': ('여러 계열사 지분을 가진 지주회사이면서 IT 시스템 구축 사업도 하는 회사예요.', ['지주회사', '시스템통합(SI)', 'IT 컨설팅']),
    '042700': ('반도체를 만든 뒤 자르고 포장하는 후공정 장비를 만드는 회사예요.', ['반도체 후공정 장비', '반도체 금형']),
    '180640': ('다른 회사들의 지분을 갖고 경영을 관리하는 지주회사예요.', ['지주사업', '경영자문']),
    '207940': ('다른 회사의 바이오 의약품을 위탁 생산하는 회사예요.', ['바이오의약품']),
}
# 공식 최신 자료로 덮어쓰는 회사: 문장·태그·출처(source/source_url)·참고 자료(ref_label/ref_url)·확인일
OFFICIAL = {
    '034020': dict(
        summary='원자력·가스발전소에 들어가는 발전설비를 만들고, 발전소 설계·건설·유지보수 서비스를 제공하는 회사예요.',
        tags=['원자력 발전설비', '가스터빈', '발전플랜트'],
        source='두산에너빌리티 공식 홈페이지 사업 소개', source_url='https://www.doosanenerbility.com/kr',
        ref_label='2025 통합보고서',
        ref_url='https://www.doosanenerbility.com/heavy_file/management/data/overview_result/report/2025_report_kr.pdf'),
    '009830': dict(
        summary='태양광 모듈·에너지 솔루션과 플라스틱 원료 같은 기초 화학제품을 만드는 회사예요.',
        tags=['태양광 모듈·에너지', '석유화학 제품'],
        source='한화솔루션 공식 홈페이지 사업 소개', source_url='https://www.hanwhasolutions.com/ko/',
        ref_label='2025 지속가능경영보고서',
        ref_url='https://www.hanwhasolutions.com/static/ko/data/Hanwha_Solutions_Sustainability_Report_2025.pdf'),
}
VERB_ONLY = {'제조', '도매', '소매', '도소매', '판매', '수출', '수입', '수출입', '무역', '임대', '등', '기타', '-'}


def split_products(text):
    """'A,B(C,D),E 제조,도매' → ['A', 'B(C,D)', 'E'] : 괄호 안 쉼표는 나누지 않고, 동사뿐인 조각은 빼요"""
    if not isinstance(text, str) or not text.strip() or text.strip() == '-':
        return []
    parts, buf, depth = [], '', 0
    for ch in text:
        if ch in '([':
            depth += 1
        elif ch in ')]':
            depth = max(0, depth - 1)
        if ch in ',/;' and depth == 0:
            parts.append(buf)
            buf = ''
        else:
            buf += ch
    parts.append(buf)
    out = []
    for p in parts:
        p = re.sub(r'\s+', ' ', p).strip(' ·.')
        p = re.sub(r'\s*(제조|도매|소매|도소매|판매|수출입|수출|제품)( 등)?$', '', p).strip()
        p = re.sub(r'\s*(등|외)$', '', p).strip()
        if p and p not in VERB_ONLY and p not in out:
            out.append(p)
    return out


def josa(word, a, b):
    """받침 있으면 a, 없으면 b (한글이 아니면 a(b))"""
    w = re.sub(r'\([^()]*\)$', '', word.strip()).strip() or word.strip()   # 끝 괄호는 빼고 판단
    ch = w[-1:] if w else ''
    if '가' <= ch <= '힣':
        return a if (ord(ch) - 0xAC00) % 28 else b
    return f'{a}({b})'


def industry_sentence(industry):
    if not isinstance(industry, str) or not industry.strip():
        return ''
    ind = industry.split(';')[0].strip()
    ind = re.sub(r'^(그외 기타|그 외 기타|기타)\s+', '', ind)
    for suffix, verb in [('제조업', '만드는'), ('건조업', '만드는')]:
        if ind.endswith(suffix):
            stem = ind[: -len(suffix)].strip()
            return f'{stem}{josa(stem, "을", "를")} {verb} 회사예요.'
    for suffix in ('도매업', '소매업', '판매업'):
        if ind.endswith(suffix):
            stem = ind[: -len(suffix)].strip()
            return f'{stem}{josa(stem, "을", "를")} 파는 회사예요.'
    stem = ind[:-1] if ind.endswith('업') else ind
    return f'{stem} 분야의 회사예요.'


def build(listing_path, collected_at):
    fin = pd.read_csv(ROOT / 'data' / '재무_2026.csv', dtype=str, encoding='utf-8-sig')
    fin['code'] = fin['종목코드'].str.strip().str.upper().str.replace(r'^A(?=[0-9A-Z]{6}$)', '', regex=True).str.zfill(6)
    base = fin.sort_values('회계연도').drop_duplicates('code', keep='last')[['code', '종목명']].rename(columns={'종목명': 'name'})
    kind = pd.read_csv(listing_path, dtype=str, encoding='utf-8-sig').drop_duplicates('Code').set_index('Code')
    rows = []
    for r in base.itertuples():
        row = dict(code=r.code, name=r.name, status='missing', kind_name='', industry='', products='',
                   summary='', tags='', homepage='', source=SOURCE, source_url=SOURCE_URL, collected_at=collected_at,
                   ref_label='', ref_url='', written='')
        if r.code in kind.index:
            k = kind.loc[r.code]
            row['kind_name'] = k['Name']
            if str(k['Name']).strip() != str(r.name).strip():
                row['status'] = 'name_mismatch'          # 이름이 달라 같은 회사인지 확정하지 않아요
            else:
                row['status'] = 'ok'
                row['industry'] = (k.get('Industry') or '') if isinstance(k.get('Industry'), str) else ''
                row['products'] = (k.get('Products') or '') if isinstance(k.get('Products'), str) else ''
                hp = k.get('HomePage')
                row['homepage'] = hp.strip() if isinstance(hp, str) and hp.strip().startswith('http') else ''
                tags = split_products(row['products'])[:3]
                if r.code in OFFICIAL:
                    o = OFFICIAL[r.code]
                    row['summary'], tags = o['summary'], o['tags']
                    row.update(source=o['source'], source_url=o['source_url'], ref_label=o['ref_label'], ref_url=o['ref_url'])
                    row['written'] = 'official'
                elif r.code in MANUAL:
                    row['summary'], tags = MANUAL[r.code][0], MANUAL[r.code][1]
                    row['written'] = 'manual'
                else:
                    s1 = industry_sentence(row['industry'])
                    s2 = f'주요 제품·서비스로 {", ".join(tags)} 등이 있어요.' if tags else ''
                    row['summary'] = ' '.join(x for x in [s1, s2] if x)
                    row['written'] = 'template'
                row['tags'] = '|'.join(tags)
                if not row['summary']:
                    row['status'] = 'no_text'
        rows.append(row)
    out = pd.DataFrame(rows).sort_values('code')
    out.to_csv(OUT, index=False, encoding='utf-8-sig')
    return out


if __name__ == '__main__':
    src = sys.argv[1] if len(sys.argv) > 1 else str(ROOT / 'data' / 'raw' / 'krx_desc_20261114.csv')
    day = sys.argv[2] if len(sys.argv) > 2 else '2026-11-14'
    df = build(src, day)
    print(df['status'].value_counts().to_dict(), '→', OUT)
