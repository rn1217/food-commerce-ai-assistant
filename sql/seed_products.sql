USE food_commerce;

INSERT INTO products (
    product_id,
    name,
    category,
    price,
    description,
    sweetness,
    packaging,
    storage_method,
    gift_available
)
VALUES
(
    1,
    '담백한 한과 선물 세트',
    '한과',
    28000,
    '개별포장된 담백한 맛의 한과 선물 세트',
    2,
    'individual',
    'room',
    TRUE
),
(
    2,
    '꿀 약과 선물 세트',
    '한과',
    24000,
    '달콤한 꿀 약과를 개별포장한 선물 세트',
    5,
    'individual',
    'room',
    TRUE
),
(
    3,
    '구운 견과 선물 세트',
    '견과',
    32000,
    '구운 견과를 하나의 용기에 담은 선물 세트',
    1,
    'bulk',
    'room',
    TRUE
),
(
    4,
    '담백한 현미 떡',
    '떡',
    12000,
    '한 개씩 포장한 일상 간식용 현미 떡',
    1,
    'individual',
    'frozen',
    FALSE
),
(
    5,
    '개별포장 견과 선물 세트',
    '견과',
    35000,
    '한 봉지씩 나누어 포장한 견과 선물 세트',
    1,
    'individual',
    'room',
    TRUE
);