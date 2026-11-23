"""O mundo real: ruas e rio do OpenStreetMap com a altimetria de um DEM.

Pipeline (offline): `osm` lê os dados → `dem` dá a elevação → `graph`
constrói o grafo jogável (interseções, ruas com perfil de altimetria, acesso
por desporto) → `navigation` move o atleta nele e sugere a rota mais rápida.
"""
