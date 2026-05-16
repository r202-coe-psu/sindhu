from flask import request

import math


def manage_pagination(datalen, items_per_page, current_page):
    pages = []
    print(datalen, items_per_page)
    max_page = math.ceil(datalen / items_per_page)
    length_page = 10
    pading_page = int(length_page * 0.3)
    if max_page <= length_page:
        pages.extend(range(1, max_page + 1))
    elif current_page <= pading_page + 1:
        pages.extend(range(1, length_page + 1))
        pages.extend(["...", max_page])
    elif current_page in range(max_page - pading_page, max_page + 1):
        pages.extend([1, "..."])
        pages.extend(range(max_page - length_page + 1, max_page + 1))
    else:
        pages.extend([1, "..."])
        pages.extend(range(current_page - pading_page, current_page + pading_page + 1))
        pages.extend(["...", max_page])
    return pages


# @caches.cache.memoize(timeout=600)
def get_paginate(data, items_per_page=20):
    page = 1
    if request.method != "POST":
        page = int(request.args.get("page", default=1))
    offset = (page - 1) * items_per_page
    datalen = len(data)  # หาจำนวน list ที่ต้องการมาแบ่ง
    data = data[offset : offset + items_per_page]
    paginate = manage_pagination(
        datalen, items_per_page, page
    )  # ทำการแบ่ง list ออกเป็นหน้า ๆ
    return dict(
        data=data,
        paginate=paginate,
        datalen=datalen,
        items_per_page=items_per_page,
    )


def get_paginates(data, count, current_page, limit=50):
    paginate = manage_pagination(count, limit, current_page)
    return dict(data=data, paginate=paginate, datalen=count, items_per_page=limit)


def get_paginate_by_integer(items, reversed=False, items_per_page=100):
    page = int(request.args.get("page", default=1))
    offset = (page - 1) * items_per_page
    datalen = items
    items = sorted(range(offset, offset + items_per_page + 1), reverse=reversed)
    pagiante = manage_pagination(datalen, items_per_page, page)
    return dict(
        items=items, pagiante=pagiante, datalen=datalen, items_per_page=items_per_page
    )
