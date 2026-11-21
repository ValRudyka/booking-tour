"""Generate docs/er_diagram.puml from the SQLAlchemy models, so the diagram always matches the code.

Usage (from backend/):  python -m scripts.generate_er
Render: PlantUML (VS Code extension "PlantUML" or plantuml.jar -tpng).
"""
from pathlib import Path

from sqlalchemy import CheckConstraint

import app.models as models
from app.models import Base

GROUPS = {  # module -> (package title, colour)
    "app.models.users": ("Користувачі", "#EEF4FB"),
    "app.models.reference": ("Довідники та налаштування", "#F3F3F3"),
    "app.models.catalog": ("Каталог", "#EEF8EE"),
    "app.models.orders": ("Замовлення", "#FDF3E7"),
    "app.models.finance": ("Фінанси, відгуки, аудит", "#F7EEF8"),
}


def col_type(col) -> str:
    t = col.type
    name = type(t).__name__.lower()
    if name == "enum":
        return "enum"
    if name in ("string", "varchar"):
        return f"varchar({t.length})" if t.length else "varchar"
    if name == "numeric":
        return f"numeric({t.precision},{t.scale})"
    if name == "datetime":
        return "timestamptz"
    return {"integer": "int", "smallinteger": "smallint", "boolean": "bool"}.get(name, name)


def main() -> None:
    mappers = {m.class_.__table__.name: m.class_ for m in Base.registry.mappers}
    lines = [
        "@startuml", "skinparam defaultFontName DejaVu Sans", "skinparam defaultFontSize 12",
        "skinparam shadowing false", "skinparam linetype ortho", "hide circle", "hide methods",
        "skinparam class {", " BackgroundColor #FBFBFB", " BorderColor #555555", "}",
    ]
    by_module: dict[str, list] = {}
    for table_name, cls in sorted(mappers.items()):
        by_module.setdefault(cls.__module__, []).append(cls.__table__)
    for module, (title, colour) in GROUPS.items():
        lines.append(f'package "{title}" {colour} {{')
        for table in by_module.get(module, []):
            lines.append(f"entity {table.name} {{")
            pk = [c for c in table.columns if c.primary_key]
            rest = [c for c in table.columns if not c.primary_key]
            for c in pk:
                fk = ",FK" if c.foreign_keys else ""
                lines.append(f" * {c.name} : {col_type(c)} <<PK{fk}>>")
            lines.append(" --")
            for c in rest:
                tags = []
                if c.foreign_keys:
                    tags.append("FK")
                if c.unique:
                    tags.append("UQ")
                tag = f" <<{','.join(tags)}>>" if tags else ""
                star = "*" if not c.nullable else " "
                lines.append(f" {star} {c.name} : {col_type(c)}{tag}")
            lines.append("}")
        lines.append("}")
    seen = set()
    for table in Base.metadata.sorted_tables:
        for c in table.columns:
            for fk in c.foreign_keys:
                parent = fk.column.table.name
                key = (parent, table.name)
                if key in seen or parent == table.name:
                    continue
                seen.add(key)
                one = "|o" if c.nullable else "||"
                many = "o|" if c.unique else "o{"
                lines.append(f"{parent} {one}--{many} {table.name}")
    lines.append("@enduml")
    out = Path(__file__).resolve().parents[2] / "docs" / "er_diagram.puml"
    out.write_text("\n".join(lines) + "\n", encoding="utf-8")
    checks = sum(isinstance(c, CheckConstraint) for t in Base.metadata.tables.values()
                 for c in t.constraints)
    print(f"{out}: {len(mappers)} tables, {len(seen)} relations, {checks} named CHECK constraints")


if __name__ == "__main__":
    assert models  # imported for side effects (all models registered)
    main()
