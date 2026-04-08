from fastapi import APIRouter

from routes.api.auth import router as auth_router
from routes.api.admin_salles import router as admin_salles_router
from routes.api.admin_stations import router as admin_stations_router
from routes.api.admin_users import router as admin_users_router
from routes.api.admin_offers import router as admin_offers_router
from routes.api.super_admin import router as super_admin_router
from routes.api.public import router as public_router
from routes.api.leftovers import router as leftovers_router

router = APIRouter(tags=["api"])

router.include_router(auth_router)
router.include_router(admin_salles_router)
router.include_router(admin_stations_router)
router.include_router(admin_users_router)
router.include_router(admin_offers_router)
router.include_router(super_admin_router)
router.include_router(public_router)
router.include_router(leftovers_router)
