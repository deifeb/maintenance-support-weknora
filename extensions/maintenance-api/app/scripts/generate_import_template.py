from app.core.config import SERVICE_ROOT
from app.importers.template import save_template


def main() -> None:
    path = save_template(SERVICE_ROOT / "templates" / "master_data_import_template.xlsx")
    print(path)


if __name__ == "__main__":
    main()
