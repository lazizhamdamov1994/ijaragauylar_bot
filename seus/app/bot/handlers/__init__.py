from functools import lru_cache

from aiogram import Router

from app.bot.handlers import buyer, channel, common, my_products, orders, product_add, registration


@lru_cache(maxsize=1)
def build_router() -> Router:
    root = Router()
    # Tartib muhim: avval umumiy (bekor qilish), keyin aniq bo'limlar, oxirida "tushunmadim"
    root.include_routers(
        common.router,
        buyer.router,
        registration.router,
        channel.router,
        product_add.router,
        my_products.router,
        orders.router,
        common.fallback_router,
    )
    return root
