from fastapi import APIRouter, HTTPException
from typing import Dict, Any
import os
from io import BytesIO
from fastapi.responses import StreamingResponse

import pandas as pd
import networkx as nx
import matplotlib.pyplot as plt

from .utils import load_csv

router = APIRouter()


def build_social_graph() -> nx.Graph:
    df = load_csv('fau_clinic_recommender_system.csv')
    G = nx.Graph()
    # parse hobbies into sets
    df['hobbies_set'] = df['hobbies'].fillna('').apply(lambda s: {x.strip().lower() for x in s.split(',') if x.strip()})
    df['sports'] = df['sports'].fillna('').str.lower()
    # add nodes
    for _, row in df.iterrows():
        G.add_node(row['id'], team=row.get('teams', ''), experience=row.get('previous_experience', ''))
    # connect by team (clique per team)
    for team, members in df.groupby('teams'):
        ids = list(members['id'])
        for i in range(len(ids)):
            for j in range(i+1, len(ids)):
                G.add_edge(ids[i], ids[j], weight=G.get_edge_data(ids[i], ids[j], {}).get('weight',0)+2, reason='team')
    # connect by shared hobbies/sports
    ids = df['id'].tolist()
    for i in range(len(df)):
        for j in range(i+1, len(df)):
            a = df.iloc[i]; b = df.iloc[j]
            common_h = a['hobbies_set'].intersection(b['hobbies_set'])
            w = 0
            if common_h:
                w += len(common_h)
            if a['sports'] and a['sports'] == b['sports']:
                w += 1
            if w > 0:
                if G.has_edge(a['id'], b['id']):
                    G[a['id']][b['id']]['weight'] += w
                    G[a['id']][b['id']]['reason'] += '+hobby'
                else:
                    G.add_edge(a['id'], b['id'], weight=w, reason='hobby')
    return G


@router.get('/analysis')
def social_analysis():
    try:
        G = build_social_graph()
    except HTTPException as e:
        return {'error': str(e.detail)}
    # centrality measures
    deg = nx.degree_centrality(G)
    btw = nx.betweenness_centrality(G)
    eig = nx.eigenvector_centrality_numpy(G) if len(G)>0 else {}
    # isolated nodes
    isolated = list(nx.isolates(G))
    # influential: top 10 by degree
    top_deg = sorted(deg.items(), key=lambda x: x[1], reverse=True)[:10]
    top_btw = sorted(btw.items(), key=lambda x: x[1], reverse=True)[:10]
    return {
        'nodes': [{'id': n, 'team': G.nodes[n].get('team'), 'degree': deg.get(n,0), 'betweenness': btw.get(n,0), 'eigenvector': eig.get(n,0)} for n in G.nodes],
        'isolated': isolated,
        'top_by_degree': [{'id':k,'score':v} for k,v in top_deg],
        'top_by_betweenness': [{'id':k,'score':v} for k,v in top_btw]
    }


@router.get('/graph.png')
def social_graph_png():
    try:
        G = build_social_graph()
    except HTTPException as e:
        raise e
    plt.figure(figsize=(10,8))
    pos = nx.spring_layout(G, seed=42)
    teams = {n: G.nodes[n].get('team','') for n in G.nodes}
    team_colors = {}
    colors = ['#1f78b4','#33a02c','#e31a1c','#ff7f00','#6a3d9a','#b15928']
    for i, t in enumerate(sorted(set(teams.values()))):
        team_colors[t] = colors[i % len(colors)]
    node_colors = [team_colors.get(teams[n], '#999999') for n in G.nodes]
    deg = dict(G.degree())
    sizes = [50 + deg.get(n,0)*30 for n in G.nodes]
    nx.draw_networkx_nodes(G, pos, node_size=sizes, node_color=node_colors)
    nx.draw_networkx_edges(G, pos, alpha=0.5)
    nx.draw_networkx_labels(G, pos, font_size=8)
    plt.axis('off')
    buf = BytesIO()
    plt.tight_layout()
    plt.savefig(buf, format='png', dpi=150)
    plt.close()
    buf.seek(0)
    return StreamingResponse(buf, media_type='image/png')
