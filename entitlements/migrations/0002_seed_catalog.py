from django.db import migrations


CATALOG = {
    "Digital": ["web_access"],
    "Print": ["web_access", "print_magazine"],
    "Premium": ["web_access", "print_magazine", "ad_free"],
}


def seed_catalog(apps, schema_editor):
    Feature = apps.get_model("entitlements", "Feature")
    Product = apps.get_model("entitlements", "Product")

    feature_names = {name for names in CATALOG.values() for name in names}
    features = {
        name: Feature.objects.create(name=name) for name in sorted(feature_names)
    }

    for product_name, feature_list in CATALOG.items():
        product = Product.objects.create(name=product_name)
        product.features.set([features[n] for n in feature_list])


def unseed_catalog(apps, schema_editor):
    Feature = apps.get_model("entitlements", "Feature")
    Product = apps.get_model("entitlements", "Product")
    Product.objects.filter(name__in=CATALOG.keys()).delete()
    Feature.objects.filter(
        name__in={n for names in CATALOG.values() for n in names}
    ).delete()


class Migration(migrations.Migration):
    dependencies = [
        ("entitlements", "0001_initial"),
    ]

    operations = [
        migrations.RunPython(seed_catalog, unseed_catalog),
    ]
