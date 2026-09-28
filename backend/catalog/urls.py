from django.urls import path

from . import views as v
from .database_views import DatabaseTableRowsView, DatabaseTablesView


urlpatterns = [
    path("health", v.HealthView.as_view()),
    path("database/tables", DatabaseTablesView.as_view()),
    path("database/tables/<str:table_name>", DatabaseTableRowsView.as_view()),
    path("catalog/entities", v.CatalogEntitiesView.as_view()),
    path("catalog/entities/<int:entity_id>", v.CatalogEntityView.as_view()),
    path("catalog/search", v.CatalogSearchView.as_view()),
    path("catalog/entities/<int:entity_id>/isbns", v.IsbnAttachView.as_view()),
    path("catalog/isbn/<str:isbn>", v.IsbnLookupView.as_view()),
    path("collections/<int:collection_id>", v.CollectionView.as_view()),
    path("collections/<int:collection_id>/items", v.CollectionItemsView.as_view()),
    path("creators", v.CreatorsView.as_view()),
    path("reading-lists", v.ReadingListsView.as_view()),
    path("reading-lists/<int:list_id>", v.ReadingListView.as_view()),
    path("reading-lists/<int:list_id>/items", v.ReadingListItemsView.as_view()),
    path("reading-map/entities", v.ReadingMapStageEntitiesView.as_view()),
    path("categories", v.CategoriesView.as_view()),
    path("catalog/entities/<int:entity_id>/categories", v.EntityCategoryView.as_view()),
    path("works/<int:entity_id>/difficulty", v.WorkProfileView.as_view()),
    path("works/<int:entity_id>/ability-requirement", v.WorkRequirementView.as_view()),
    path("children", v.ChildrenView.as_view()),
    path("children/<int:child_id>", v.ChildView.as_view()),
    path("children/<int:child_id>/abilities", v.ChildAbilitiesView.as_view()),
    path("children/<int:child_id>/abilities/<str:language_code>", v.ChildAbilityView.as_view()),
    path("children/<int:child_id>/annotations", v.ChildAnnotationsView.as_view()),
    path("children/<int:child_id>/entities/<int:entity_id>", v.ChildAnnotationView.as_view()),
    path("catalog/entities/<int:entity_id>/source-stats", v.SourceStatsView.as_view()),
]
