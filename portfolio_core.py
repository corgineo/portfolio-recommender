"""C 화면의 순수 계산. B의 성과 계산은 별도 콜백으로 연결한다."""
from decimal import Decimal, ROUND_FLOOR
import math
import pandas as pd


def validate_assets(assets):
    required = {'ticker', 'name', 'asset_class', 'price', 'as_of', 'source'}
    if not required.issubset(assets.columns):
        raise ValueError(f'필수 열 누락: {sorted(required - set(assets.columns))}')
    result = assets.copy()
    if result.empty or result['ticker'].isna().any():
        raise ValueError('상품 목록과 종목코드를 확인해 줘.')
    result['ticker'] = result['ticker'].astype(str)
    if result['ticker'].str.strip().eq('').any() or result['ticker'].duplicated().any():
        raise ValueError('종목코드는 비어 있거나 중복될 수 없어.')
    for col in ['name', 'asset_class', 'as_of', 'source']:
        if result[col].isna().any() or result[col].astype(str).str.strip().eq('').any():
            raise ValueError(f'{col} 열에 빈 값이 있어.')
    result['price'] = pd.to_numeric(result['price'], errors='coerce')
    if not result['price'].map(lambda x: math.isfinite(x) and x > 0).all():
        raise ValueError('가격은 0보다 큰 유효한 숫자여야 해.')
    if pd.to_datetime(result['as_of'], errors='coerce').isna().any():
        raise ValueError('기준일은 YYYY-MM-DD 형식으로 넣어 줘.')
    return result


def validate_weights(weights, tickers):
    unknown = set(weights) - set(tickers)
    if unknown:
        raise ValueError(f'알 수 없는 종목코드: {sorted(unknown)}')
    values = {t: float(weights.get(t, 0)) for t in tickers}
    if any(not math.isfinite(v) or v < 0 or v > 100 for v in values.values()):
        raise ValueError('비중은 0~100 사이의 숫자여야 해.')
    if sum(values.values()) > 100 + 1e-8:
        raise ValueError('비중 합계가 100%를 초과했어.')
    return values


def allocate(assets, weights, budget):
    """원화, 정수 주수, 매수 비용 제외. 반올림 초과 지출 방지를 위해 Decimal 사용."""
    assets = validate_assets(assets)
    weights = validate_weights(weights, assets.ticker.tolist())
    amount = Decimal(str(budget))
    if not amount.is_finite() or amount <= 0:
        raise ValueError('예산은 0보다 커야 해.')
    rows = []
    total = Decimal('0')
    for row in assets.itertuples(index=False):
        target = amount * Decimal(str(weights[row.ticker])) / 100
        price = Decimal(str(row.price))
        qty = int((target / price).to_integral_value(rounding=ROUND_FLOOR))
        spent = price * qty
        total += spent
        rows.append(dict(ticker=row.ticker, name=row.name, asset_class=row.asset_class,
                         target_pct=weights[row.ticker], target_amount=float(target),
                         price=float(price), quantity=qty, purchase_amount=float(spent),
                         actual_pct=float(spent / amount * 100), as_of=row.as_of, source=row.source))
    return pd.DataFrame(rows), float(amount - total)
