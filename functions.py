import geopandas as gpd
import osmnx as ox
import networkx as nx
import pandas as pd
import geopandas as gpd
import numpy as np
from shapely.geometry import Point, Polygon, LineString


def gdf_to_only_points(gdf):
    gdf['geometry_init'] = gdf['geometry'] 
    gdf['geometry_init'] = gdf.loc[:, 'geometry']
    
    for i, row in gdf.iterrows():
        if row.geometry.geom_type != "Point":
            new_geometry = row.geometry.centroid
            gdf.at[i, 'geometry'] = new_geometry


def get_coords_from_gdf(gdf):
    geometries =  gdf.geometry
    coords = []
    for geom in geometries: 
        x = geom.x
        y = geom.y
        
        coord = (y,x)
        coords.append(coord)
        
    return coords

def get_nearest_node(input_coordinate, G):
    nodes = ox.utils_graph.graph_to_gdfs(G, nodes=True, edges=False, node_geometry=True)

    distance = nodes.apply(lambda x: np.sqrt((x.y - input_coordinate[0])**2 + (x.x - input_coordinate[1])**2) , axis = 1)
    output = distance.idxmin()
    return output


def get_nearest_nodes(input_coordinates, G):
    nodes = ox.utils_graph.graph_to_gdfs(G, nodes=True, edges=False, node_geometry=True)
    
    output = []
    for i in range(len(input_coordinates)):
        distances = nodes.apply(lambda x: np.sqrt((x.y - input_coordinates[i][0])**2 + (x.x - input_coordinates[i][1])**2) , axis = 1)
        nearest_node = distances.idxmin()
        output.append(nearest_node)
    return output


def dist_to_nearest_nature(coords, water, parks):
    
    #coords = list(gdf["coordinates"])
    polygons_water = water['geometry']
    polygons_water.reset_index(inplace = True, drop = True)
    
    polygons_parks = parks['geometry']
    polygons_parks.reset_index(inplace = True, drop = True)

    
    # Lists for saving results
    min_distances_to_nature = []
    nature_with_min_dist = []
    nature_type_nearest = []
    
    # Find distance to nearest polygon
    for coord in coords:
        coord = Point(coord[1], coord[0])
        # Water
        dist_to_waters = []
        for poly in polygons_water:
            if poly.geom_type == "Polygon": # Sometimes linestrings are returned, and these cannot be used
                distance = poly.exterior.distance(coord)
                dist_to_waters.append(distance)
            
            if poly.geom_type == "MultiPolygon":
                single_poly = poly.convex_hull
                distance = single_poly.exterior.distance(coord)
                dist_to_waters.append(distance)
        dist_to_nearest_water = min(dist_to_waters)
        nearest_water = polygons_water[np.argmin(dist_to_waters)]
        
        # Park areas
        dist_to_parks = []
        
        for poly in polygons_parks:
            if poly.geom_type == "Polygon": # Sometimes linestrings are returned, and these cannot be used
                distance = poly.exterior.distance(coord)
                dist_to_parks.append(distance)
            
            if poly.geom_type == "MultiPolygon":
                single_poly = poly.convex_hull
                distance = single_poly.exterior.distance(coord)
                dist_to_parks.append(distance)
        dist_to_nearest_park = min(dist_to_parks)
        nearest_park = polygons_parks[np.argmin(dist_to_parks)]
        
        # Both
        dist_to_nearest_nature = min(dist_to_nearest_water, dist_to_nearest_park)
        min_distances_to_nature.append(dist_to_nearest_nature)
        
        if dist_to_nearest_water < dist_to_nearest_park:
            nature_with_min_dist.append(nearest_water)
            nature_type_nearest.append("water")
        else:
            nature_with_min_dist.append(nearest_park)
            nature_type_nearest.append("park")
    
    return min_distances_to_nature, nature_with_min_dist, nature_type_nearest

def apply_road_use_cost(G, name_of_cost):
    for edge in G.edges:
        if type(G.edges[edge]["highway"]) == str: #meaning we are not dealing with a list
            current_string = G.edges[edge]["highway"]
            if current_string in no_go_road_types:
                G.edges[edge][name_of_cost] = G.edges[edge]["length"] * no_go_use
            if current_string in unwanted_road_types:
                G.edges[edge][name_of_cost] = G.edges[edge]["length"] * unwanted_use
            else: 
                G.edges[edge][name_of_cost] = 0
        if type(G.edges[edge]["highway"]) == list:
            current_set = set(G.edges[edge]["highway"])
            if current_set.intersection(no_go_road_types):
                G.edges[edge][name_of_cost] = G.edges[edge]["length"] * no_go_use
            if current_set.intersection(no_go_road_types):
                G.edges[edge][name_of_cost] = G.edges[edge]["length"] * unwanted_use
            else: 
                G.edges[edge][name_of_cost] = 0


def apply_speed_cost(G, name_of_cost):
    for edge in G.edges:
        if "maxspeed" in G.edges[edge]:
            if (type(G.edges[edge]["maxspeed"]) == list): # Here we take the biggest value, if more than one is listed
                float_list = [float(i) for i in G.edges[edge]["maxspeed"]]
                G.edges[edge][name_of_cost] = max(float_list) * speed_cost
            else: 
                G.edges[edge][name_of_cost] = float(G.edges[edge]["maxspeed"]) * speed_cost
        else:
            G.edges[edge][name_of_cost] = 0


def apply_gain_to_edges_in_polygons(G, geometries, name_of_gain):
    polygons = geometries['geometry']
    
    nodes_in_polygons = []
    
    # Find nodes in polygons with within function from shapely
    
    for node, data in G.nodes(data = True):
        coord = Point(data["x"], data["y"])
        for poly in polygons:
            if coord.within(poly):
                nodes_in_polygons.append(node)
    
    # Apply edge weight to edges with ends in any of these nodes
    for edge in G.edges:
        if (edge[0] in nodes_in_polygons) or (edge[1] in nodes_in_polygons): 
            G.edges[edge][name_of_gain] = 0
        else: 
            G.edges[edge][name_of_gain] = G.edges[edge]["length"] * anti_nature_cost
            
def apply_gain_to_edges_near_polygons(G, geometries, name_of_gain):
    polygons = geometries['geometry']
    
    nodes_near_polygons = []
    
    # Find nodes in polygons with within function from shapely
    
    for node, data in G.nodes(data = True):
        coord = Point(data["x"], data["y"])
        for poly in polygons:
            if poly.geom_type == "Polygon": # Sometimes linestrings are returned, and these cannot be used
                distance = poly.exterior.distance(coord)

                if distance < 0.0005: #If distance is less than 0.5 meters (found empirically to be good)
                    nodes_near_polygons.append(node)
            
            if poly.geom_type == "MultiPolygon":
                single_poly = poly.convex_hull
                distance = single_poly.exterior.distance(coord)

                if distance < 0.0005: #If distance is less than 0.5 meters (found empirically to be good)
                    nodes_near_polygons.append(node)
                
    # Apply edge weight to edges with ends in any of these water nodes
    for edge in G.edges:
        if (edge[0] in nodes_near_polygons) or (edge[1] in nodes_near_polygons): 
            G.edges[edge][name_of_gain] = 0
        else: 
            G.edges[edge][name_of_gain] =  G.edges[edge]["length"]* anti_nature_cost
            
def sum_edge_attributes(G, attributes):
    list_total_costs = []
    for u, v, key, data in G.edges(keys=True, data=True): 
        total_cost = 0
        for att in attributes:
            total_cost = total_cost + data[att]
        data["total_cost"] = total_cost
        list_total_costs.append(total_cost)
    return list_total_costs

def graph_cols_to_float(G, cols):
    for i, j, key, data in G.edges(keys = True, data = True):
        for col in cols:
            data[col] = float(data[col])
