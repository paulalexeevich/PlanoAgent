"""
Planogram Data Schema & Models
==============================
Defines the data structures for planogram representation following 
industry-standard hierarchy: Project > Planogram > Bay (Segment) > Shelf (Fixture) > Position

Based on Blue Yonder Space Planning object hierarchy and GoPlanogram standards.
"""

from dataclasses import dataclass, field, asdict
from typing import Optional
from enum import Enum
import json


class EquipmentType(str, Enum):
    GONDOLA = "gondola"
    COOLER = "cooler"
    ENDCAP = "endcap"
    WALL_SECTION = "wall_section"
    ISLAND = "island"


class PackageType(str, Enum):
    CAN = "can"
    BOTTLE = "bottle"
    TALLBOY_CAN = "tallboy_can"
    BOMBER = "bomber"
    PACK_BOX = "pack_box"


class Orientation(str, Enum):
    FRONT = "front"
    SIDE = "side"
    TOP = "top"


@dataclass
class Product:
    """A product in the assortment catalog."""
    id: str
    upc: str
    name: str
    brand: str
    manufacturer: str
    category: str
    subcategory: str
    beer_type: str
    package_type: str
    pack_size: int
    unit_size_oz: float
    width_in: float       # Width in inches
    height_in: float      # Height in inches
    depth_in: float       # Depth in inches
    price: float
    cost: float
    abv: float
    color_hex: str = "#CCCCCC"
    weekly_units_sold: int = 0

    @property
    def margin(self) -> float:
        return self.price - self.cost

    @property
    def margin_pct(self) -> float:
        return (self.margin / self.price) * 100 if self.price > 0 else 0


@dataclass
class Position:
    """A product placement on a shelf — maps product to physical location."""
    product_id: str
    x_position: float     # X offset from left edge of shelf (inches)
    facings_wide: int = 1
    facings_high: int = 1
    facings_deep: int = 1
    orientation: str = "front"

    def total_units(self) -> int:
        return self.facings_wide * self.facings_high * self.facings_deep


@dataclass
class Shelf:
    """A fixture (shelf) within a bay."""
    shelf_number: int
    width_in: float       # Shelf width in inches
    height_in: float      # Usable height for products (clearance)
    depth_in: float       # Shelf depth in inches
    y_position: float     # Distance from floor in inches
    positions: list = field(default_factory=list)  # List[Position]
    shelf_type: str = "standard"  # standard, wire, slanted

    def used_width(self, products_map: dict) -> float:
        """Calculate total used width across all positions."""
        total = 0
        for pos in self.positions:
            product = products_map.get(pos.product_id)
            if product:
                total += product.width_in * pos.facings_wide
        return total

    def fill_rate(self, products_map: dict) -> float:
        """Percentage of shelf width used."""
        used = self.used_width(products_map)
        return (used / self.width_in) * 100 if self.width_in > 0 else 0


@dataclass
class Bay:
    """A segment/bay of the equipment (e.g., one section of a gondola)."""
    bay_number: int
    width_in: float       # Bay width in inches
    height_in: float      # Total bay height in inches
    depth_in: float       # Bay depth in inches
    shelves: list = field(default_factory=list)  # List[Shelf]
    glued_right: bool = False  # True = visually connected to the next bay (no gap)


@dataclass
class Equipment:
    """The physical fixture/equipment (gondola, cooler, endcap, etc.)."""
    id: str
    name: str
    equipment_type: str
    bays: list = field(default_factory=list)  # List[Bay]

    @property
    def total_width(self) -> float:
        return sum(bay.width_in for bay in self.bays)

    @property
    def total_shelves(self) -> int:
        return sum(len(bay.shelves) for bay in self.bays)


@dataclass
class Planogram:
    """Top-level planogram container."""
    id: str
    name: str
    category: str
    store_type: str
    effective_date: str
    equipment: Equipment = None
    products: list = field(default_factory=list)  # List[Product]
    metadata: dict = field(default_factory=dict)

    @property
    def products_map(self) -> dict:
        return {p.id: p for p in self.products}

    def total_products(self) -> int:
        return len(self.products)

    def total_positions(self) -> int:
        count = 0
        if self.equipment:
            for bay in self.equipment.bays:
                for shelf in bay.shelves:
                    count += len(shelf.positions)
        return count

    def total_facings(self) -> int:
        total = 0
        if self.equipment:
            for bay in self.equipment.bays:
                for shelf in bay.shelves:
                    for pos in shelf.positions:
                        total += pos.facings_wide
        return total

    def to_dict(self) -> dict:
        """Serialize planogram to dictionary."""
        return {
            "id": self.id,
            "name": self.name,
            "category": self.category,
            "store_type": self.store_type,
            "effective_date": self.effective_date,
            "metadata": self.metadata,
            "equipment": asdict(self.equipment) if self.equipment else None,
            "products": [asdict(p) for p in self.products]
        }

    def to_json(self, indent=2) -> str:
        """Serialize to JSON string."""
        return json.dumps(self.to_dict(), indent=indent)

    @classmethod
    def from_dict(cls, data: dict) -> 'Planogram':
        """Deserialize from dictionary.

        Tolerant of extra keys (e.g. from AI-generated JSON) — unknown
        fields are silently dropped for each dataclass.
        """
        import dataclasses as _dc

        def _safe(klass, d: dict):
            """Build *klass* from *d*, keeping only fields *klass* declares."""
            valid = {f.name for f in _dc.fields(klass)}
            return klass(**{k: v for k, v in d.items() if k in valid})

        products = [_safe(Product, p) for p in data.get("products", [])]

        equipment_data = data.get("equipment")
        equipment = None
        if equipment_data:
            bays = []
            for bay_data in equipment_data.get("bays", []):
                shelves = []
                for shelf_data in bay_data.get("shelves", []):
                    positions = [_safe(Position, pos) for pos in shelf_data.get("positions", [])]
                    shelf_data_clean = {k: v for k, v in shelf_data.items() if k != "positions"}
                    shelves.append(_safe(Shelf, {**shelf_data_clean, "positions": positions}))
                bay_data_clean = {k: v for k, v in bay_data.items() if k != "shelves"}
                bays.append(_safe(Bay, {**bay_data_clean, "shelves": shelves}))
            equip_data_clean = {k: v for k, v in equipment_data.items() if k != "bays"}
            equipment = _safe(Equipment, {**equip_data_clean, "bays": bays})

        return cls(
            id=data.get("id", "PLN-001"),
            name=data.get("name", "Planogram"),
            category=data.get("category", ""),
            store_type=data.get("store_type", ""),
            effective_date=data.get("effective_date", ""),
            equipment=equipment,
            products=products,
            metadata=data.get("metadata", {})
        )
