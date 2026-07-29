"""Import every module's models so Alembic autogenerate sees them.

A model missing from this file will be ABSENT from migrations and
autogenerate may emit a DROP for its table. One line per module.
"""

from app.db.base import Base  # noqa: F401
from app.modules.addresses import models as addresses_models  # noqa: F401

# catalogue + addresses
from app.modules.catalogue import models as catalogue_models  # noqa: F401

# fulfilment
from app.modules.delivery import models as delivery_models  # noqa: F401
from app.modules.delivery_pricing import models as delivery_pricing_models  # noqa: F401

# geo + pricing (foundation)
from app.modules.geo import models as geo_models  # noqa: F401

# identity (shipped)
from app.modules.identity import models as identity_models  # noqa: F401
from app.modules.notifications import models as notifications_models  # noqa: F401

# ops
from app.modules.ops import models as ops_models  # noqa: F401
from app.modules.orders import models as orders_models  # noqa: F401
from app.modules.payments import models as payments_models  # noqa: F401

# commerce core
from app.modules.privileges import models as privileges_models  # noqa: F401
from app.modules.returns import models as returns_models  # noqa: F401

# engagement
from app.modules.showcasing import models as showcasing_models  # noqa: F401

# supply side
from app.modules.sourcing import models as sourcing_models  # noqa: F401

__all__ = ["Base"]