"""
Exploration interactive des profils et des trajectoires individuelles.
"""

from __future__ import annotations

import json
from pathlib import Path

import geopandas as gpd
import pandas as pd

from src.core.temporal import build_member_timelines


def _destination_descriptor(destination_id: str, building_lookup: pd.DataFrame) -> tuple[str, str]:
    if destination_id == "DOMICILE":
        return "Domicile", "Résidentiel"
    if destination_id in {"EXTERIEUR", "None", None}:
        return "Extérieur commune", "Hors commune"
    if destination_id in building_lookup.index:
        row = building_lookup.loc[destination_id]
        usage = str(row.get("usage_1", ""))
        suffix = str(destination_id)[-6:]
        return f"{usage or 'Destination interne'} #{suffix}", usage or "Interne"
    return str(destination_id), "Interne"


def _profile_hourly_summary(member_timelines: pd.DataFrame) -> dict[str, list[dict[str, int]]]:
    summary: dict[str, list[dict[str, int]]] = {}
    for role, group in member_timelines.groupby("role"):
        hourly_counts = []
        for hour in range(24):
            state_series = group["timeline_states"].apply(lambda states: states[hour])
            counts = state_series.value_counts()
            hourly_counts.append(
                {
                    "hour": hour,
                    "domicile": int(counts.get("domicile", 0)),
                    "interne": int(counts.get("interne", 0)),
                    "exterieur": int(counts.get("exterieur", 0)),
                }
            )
        summary[str(role)] = hourly_counts
    return summary


def _spatial_extent_payload(member_payload: list[dict]) -> dict[str, float]:
    xs: list[float] = []
    ys: list[float] = []
    for member in member_payload:
        xs.append(member["origin_centroid"][0])
        ys.append(member["origin_centroid"][1])
        if member["assigned_destination_centroid"] is not None:
            xs.append(member["assigned_destination_centroid"][0])
            ys.append(member["assigned_destination_centroid"][1])
        for point in member["timeline_points"]:
            if point is not None:
                xs.append(point[0])
                ys.append(point[1])

    if not xs or not ys:
        return {"min_x": 0.0, "max_x": 1.0, "min_y": 0.0, "max_y": 1.0}
    return {
        "min_x": min(xs),
        "max_x": max(xs),
        "min_y": min(ys),
        "max_y": max(ys),
    }


def export_profile_activity_explorer(
    gdf_model: gpd.GeoDataFrame,
    config: dict,
    output_path: str | Path,
) -> Path:
    """
    Produit un HTML autonome pour filtrer les profils et suivre un individu.
    """
    member_timelines = build_member_timelines(gdf_model, config)
    if member_timelines.empty:
        raise ValueError("Aucune trajectoire individuelle n'a pu etre reconstruite.")

    building_lookup = gdf_model.set_index("building_id")
    member_payload = []
    for _, row in member_timelines.iterrows():
        timeline_labels = []
        timeline_usages = []
        timeline_points = []
        for destination_id in row["timeline_destinations"]:
            label, usage = _destination_descriptor(destination_id, building_lookup)
            timeline_labels.append(label)
            timeline_usages.append(usage)
            if destination_id not in {"DOMICILE", "EXTERIEUR", "None", None} and destination_id in building_lookup.index:
                centroid = building_lookup.loc[destination_id].geometry.centroid
                timeline_points.append([float(centroid.x), float(centroid.y)])
            elif destination_id == "DOMICILE":
                timeline_points.append(row["origin_centroid"])
            else:
                timeline_points.append(None)

        home_row = building_lookup.loc[row["home_building_id"]]
        member_payload.append(
            {
                "member_id": row["member_id"],
                "role": row["role"],
                "home_building_id": row["home_building_id"],
                "home_usage": str(home_row.get("usage_1", "")),
                "assigned_destination_id": row["assigned_destination_id"],
                "assigned_destination_usage": row["assigned_destination_usage"],
                "origin_centroid": row["origin_centroid"],
                "assigned_destination_centroid": row["assigned_destination_centroid"],
                "timeline_destinations": row["timeline_destinations"],
                "timeline_states": row["timeline_states"],
                "timeline_labels": timeline_labels,
                "timeline_usages": timeline_usages,
                "timeline_points": timeline_points,
            }
        )

    role_counts = (
        member_timelines["role"]
        .value_counts()
        .sort_index()
        .to_dict()
    )
    payload = {
        "scenario_name": config.get("scenario", {}).get("name", "scenario"),
        "reference_hour": int(config.get("scenario", {}).get("reference_hour", 0)),
        "profile_hourly_summary": _profile_hourly_summary(member_timelines),
        "role_counts": {str(key): int(value) for key, value in role_counts.items()},
        "members": member_payload,
        "spatial_extent": _spatial_extent_payload(member_payload),
    }

    html_content = f"""<!DOCTYPE html>
<html lang="fr">
<head>
  <meta charset="utf-8">
  <title>Explorateur des profils MOGEC</title>
  <style>
    :root {{
      --bg: #f7f5ef;
      --card: #fffdf8;
      --ink: #102226;
      --muted: #5d6c73;
      --line: #d7d1c4;
      --accent: #1f4e79;
      --home: #5b8e7d;
      --internal: #d97706;
      --external: #b03a2e;
    }}
    body {{
      margin: 0;
      font-family: "IBM Plex Sans", "Segoe UI", sans-serif;
      background: linear-gradient(180deg, #f7f5ef 0%, #ece7dc 100%);
      color: var(--ink);
    }}
    .page {{
      max-width: 1380px;
      margin: 0 auto;
      padding: 28px 24px 40px;
    }}
    .hero {{
      display: flex;
      justify-content: space-between;
      align-items: end;
      gap: 24px;
      margin-bottom: 20px;
    }}
    .hero h1 {{
      margin: 0;
      font-size: 2rem;
    }}
    .hero p {{
      margin: 8px 0 0;
      color: var(--muted);
      max-width: 760px;
    }}
    .controls {{
      display: grid;
      grid-template-columns: repeat(3, minmax(220px, 1fr));
      gap: 14px;
      margin-bottom: 18px;
    }}
    .card {{
      background: var(--card);
      border: 1px solid rgba(16, 34, 38, 0.10);
      border-radius: 18px;
      box-shadow: 0 10px 35px rgba(16, 34, 38, 0.06);
      padding: 16px 18px;
    }}
    label {{
      display: block;
      font-size: 0.84rem;
      color: var(--muted);
      margin-bottom: 6px;
    }}
    select, input[type="range"] {{
      width: 100%;
    }}
    .summary-grid {{
      display: grid;
      grid-template-columns: repeat(5, minmax(120px, 1fr));
      gap: 12px;
      margin-bottom: 18px;
    }}
    .summary-grid .metric-value {{
      font-size: 1.9rem;
      font-weight: 700;
      margin-top: 8px;
    }}
    .layout {{
      display: grid;
      grid-template-columns: 1.15fr 0.85fr;
      gap: 18px;
    }}
    .panel-grid {{
      display: grid;
      gap: 18px;
    }}
    .timeline-table {{
      width: 100%;
      border-collapse: collapse;
      font-size: 0.92rem;
    }}
    .timeline-table th, .timeline-table td {{
      padding: 8px 10px;
      border-bottom: 1px solid var(--line);
      text-align: left;
    }}
    .state-chip {{
      display: inline-block;
      padding: 2px 8px;
      border-radius: 999px;
      font-size: 0.78rem;
      font-weight: 600;
    }}
    .state-domicile {{ background: rgba(91, 142, 125, 0.16); color: var(--home); }}
    .state-interne {{ background: rgba(217, 119, 6, 0.16); color: var(--internal); }}
    .state-exterieur {{ background: rgba(176, 58, 46, 0.16); color: var(--external); }}
    .stack-row {{
      display: grid;
      grid-template-columns: 44px 1fr 140px;
      align-items: center;
      gap: 10px;
      margin-bottom: 8px;
    }}
    .stack-bar {{
      display: flex;
      height: 16px;
      border-radius: 999px;
      overflow: hidden;
      background: #ece7dc;
    }}
    .stack-home {{ background: var(--home); }}
    .stack-interne {{ background: var(--internal); }}
    .stack-exterieur {{ background: var(--external); }}
    .track-meta {{
      display: grid;
      grid-template-columns: repeat(2, minmax(140px, 1fr));
      gap: 10px;
      margin-bottom: 12px;
    }}
    .track-meta strong {{
      display: block;
      font-size: 0.8rem;
      color: var(--muted);
      margin-bottom: 4px;
    }}
    #trackCanvas {{
      width: 100%;
      height: 320px;
      border: 1px solid var(--line);
      border-radius: 16px;
      background: linear-gradient(180deg, #fffef9 0%, #f3eee3 100%);
    }}
    .legend {{
      display: flex;
      gap: 14px;
      flex-wrap: wrap;
      margin-top: 12px;
      color: var(--muted);
      font-size: 0.85rem;
    }}
    .legend span::before {{
      content: "";
      display: inline-block;
      width: 10px;
      height: 10px;
      border-radius: 50%;
      margin-right: 6px;
      vertical-align: middle;
    }}
    .legend-home::before {{ background: var(--home); }}
    .legend-interne::before {{ background: var(--internal); }}
    .legend-exterieur::before {{ background: var(--external); }}
    @media (max-width: 1080px) {{
      .layout {{
        grid-template-columns: 1fr;
      }}
      .summary-grid {{
        grid-template-columns: repeat(2, minmax(140px, 1fr));
      }}
      .controls {{
        grid-template-columns: 1fr;
      }}
    }}
  </style>
</head>
<body>
  <div class="page">
    <div class="hero">
      <div>
        <h1>Explorateur des profils et activites</h1>
        <p>Scenario <strong>{payload["scenario_name"]}</strong>. Filtre un profil, choisis un individu, puis fais varier l'heure pour suivre sa position et son activite. T0 correspond a h{payload["reference_hour"]:02d}.</p>
      </div>
    </div>

    <div class="summary-grid" id="roleCards"></div>

    <div class="controls">
      <div class="card">
        <label for="roleSelect">Filtrer par profil</label>
        <select id="roleSelect"></select>
      </div>
      <div class="card">
        <label for="memberSelect">Suivre une personne</label>
        <select id="memberSelect"></select>
      </div>
      <div class="card">
        <label for="hourSlider">Heure observee <span id="hourLabel">h00</span></label>
        <input type="range" id="hourSlider" min="0" max="23" step="1" value="{payload["reference_hour"]}">
      </div>
    </div>

    <div class="layout">
      <div class="panel-grid">
        <div class="card">
          <h2>Distribution horaire du profil</h2>
          <div id="profileStack"></div>
          <div class="legend">
            <span class="legend-home">Domicile</span>
            <span class="legend-interne">Interne commune</span>
            <span class="legend-exterieur">Hors commune</span>
          </div>
        </div>
        <div class="card">
          <h2>Journal d'activite individuel</h2>
          <table class="timeline-table">
            <thead>
              <tr><th>Heure</th><th>Etat</th><th>Lieu</th><th>Type</th></tr>
            </thead>
            <tbody id="timelineBody"></tbody>
          </table>
        </div>
      </div>

      <div class="panel-grid">
        <div class="card">
          <h2>Suivi dynamique</h2>
          <div class="track-meta">
            <div><strong>Personne</strong><span id="memberId"></span></div>
            <div><strong>Profil</strong><span id="memberRole"></span></div>
            <div><strong>Domicile</strong><span id="memberHome"></span></div>
            <div><strong>Destination principale</strong><span id="memberDest"></span></div>
            <div><strong>Etat a l'heure courante</strong><span id="memberState"></span></div>
            <div><strong>Lieu courant</strong><span id="memberCurrent"></span></div>
          </div>
          <svg id="trackCanvas" viewBox="0 0 420 320" preserveAspectRatio="xMidYMid meet"></svg>
          <div class="legend">
            <span class="legend-home">Domicile</span>
            <span class="legend-interne">Destination interne</span>
            <span class="legend-exterieur">Extérieur</span>
          </div>
        </div>
      </div>
    </div>
  </div>

  <script>
    const explorerData = {json.dumps(payload, ensure_ascii=False)};
    const roleOrder = Object.keys(explorerData.role_counts).sort();
    const members = explorerData.members;
    const extent = explorerData.spatial_extent;

    const roleSelect = document.getElementById('roleSelect');
    const memberSelect = document.getElementById('memberSelect');
    const hourSlider = document.getElementById('hourSlider');
    const hourLabel = document.getElementById('hourLabel');

    function formatHour(hour) {{
      return `h${{String(hour).padStart(2, '0')}}`;
    }}

    function normalizePoint(point) {{
      if (!point) return null;
      const width = Math.max(extent.max_x - extent.min_x, 1);
      const height = Math.max(extent.max_y - extent.min_y, 1);
      const x = 30 + ((point[0] - extent.min_x) / width) * 360;
      const y = 290 - ((point[1] - extent.min_y) / height) * 250;
      return [x, y];
    }}

    function buildRoleCards() {{
      const container = document.getElementById('roleCards');
      container.innerHTML = '';
      roleOrder.forEach((role) => {{
        const card = document.createElement('div');
        card.className = 'card';
        card.innerHTML = `<div>${{role}}</div><div class="metric-value">${{explorerData.role_counts[role]}}</div>`;
        container.appendChild(card);
      }});
    }}

    function populateRoleSelect() {{
      roleSelect.innerHTML = '';
      roleOrder.forEach((role) => {{
        const option = document.createElement('option');
        option.value = role;
        option.textContent = role;
        roleSelect.appendChild(option);
      }});
    }}

    function membersForRole(role) {{
      return members.filter((member) => member.role === role);
    }}

    function populateMemberSelect(role) {{
      const filtered = membersForRole(role);
      memberSelect.innerHTML = '';
      filtered.forEach((member) => {{
        const option = document.createElement('option');
        option.value = member.member_id;
        option.textContent = `${{member.member_id}}`;
        memberSelect.appendChild(option);
      }});
      if (filtered.length > 0) {{
        memberSelect.value = filtered[0].member_id;
      }}
    }}

    function renderProfileSummary(role) {{
      const container = document.getElementById('profileStack');
      container.innerHTML = '';
      const rows = explorerData.profile_hourly_summary[role] || [];
      const total = explorerData.role_counts[role] || 1;
      rows.forEach((row) => {{
        const wrapper = document.createElement('div');
        wrapper.className = 'stack-row';
        const domicileWidth = (row.domicile / total) * 100;
        const interneWidth = (row.interne / total) * 100;
        const exterieurWidth = (row.exterieur / total) * 100;
        wrapper.innerHTML = `
          <div>${{formatHour(row.hour)}}</div>
          <div class="stack-bar">
            <div class="stack-home" style="width:${{domicileWidth}}%"></div>
            <div class="stack-interne" style="width:${{interneWidth}}%"></div>
            <div class="stack-exterieur" style="width:${{exterieurWidth}}%"></div>
          </div>
          <div>${{row.domicile}} / ${{row.interne}} / ${{row.exterieur}}</div>
        `;
        container.appendChild(wrapper);
      }});
    }}

    function selectedMember() {{
      return members.find((member) => member.member_id === memberSelect.value);
    }}

    function renderTimeline(member) {{
      const body = document.getElementById('timelineBody');
      body.innerHTML = '';
      member.timeline_states.forEach((state, hour) => {{
        const tr = document.createElement('tr');
        tr.innerHTML = `
          <td>${{formatHour(hour)}}</td>
          <td><span class="state-chip state-${{state}}">${{state}}</span></td>
          <td>${{member.timeline_labels[hour]}}</td>
          <td>${{member.timeline_usages[hour]}}</td>
        `;
        body.appendChild(tr);
      }});
    }}

    function drawTrack(member, hour) {{
      const svg = document.getElementById('trackCanvas');
      const origin = normalizePoint(member.origin_centroid);
      const currentPoint = normalizePoint(member.timeline_points[hour]);
      svg.innerHTML = '';

      const bg = document.createElementNS('http://www.w3.org/2000/svg', 'rect');
      bg.setAttribute('x', '0');
      bg.setAttribute('y', '0');
      bg.setAttribute('width', '420');
      bg.setAttribute('height', '320');
      bg.setAttribute('fill', '#fffef9');
      svg.appendChild(bg);

      if (origin) {{
        const circle = document.createElementNS('http://www.w3.org/2000/svg', 'circle');
        circle.setAttribute('cx', origin[0]);
        circle.setAttribute('cy', origin[1]);
        circle.setAttribute('r', '7');
        circle.setAttribute('fill', '#5b8e7d');
        svg.appendChild(circle);
      }}

      if (currentPoint) {{
        const line = document.createElementNS('http://www.w3.org/2000/svg', 'line');
        line.setAttribute('x1', origin[0]);
        line.setAttribute('y1', origin[1]);
        line.setAttribute('x2', currentPoint[0]);
        line.setAttribute('y2', currentPoint[1]);
        line.setAttribute('stroke', '#1f4e79');
        line.setAttribute('stroke-width', '2');
        line.setAttribute('stroke-dasharray', '6 4');
        svg.appendChild(line);

        const current = document.createElementNS('http://www.w3.org/2000/svg', 'circle');
        current.setAttribute('cx', currentPoint[0]);
        current.setAttribute('cy', currentPoint[1]);
        current.setAttribute('r', '8');
        current.setAttribute('fill', member.timeline_states[hour] === 'domicile' ? '#5b8e7d' : '#d97706');
        svg.appendChild(current);
      }} else {{
        const note = document.createElementNS('http://www.w3.org/2000/svg', 'text');
        note.setAttribute('x', '24');
        note.setAttribute('y', '34');
        note.setAttribute('fill', '#b03a2e');
        note.textContent = 'Position courante hors commune';
        svg.appendChild(note);
      }}
    }}

    function renderMemberPanel(member, hour) {{
      document.getElementById('memberId').textContent = member.member_id;
      document.getElementById('memberRole').textContent = member.role;
      document.getElementById('memberHome').textContent = `${{member.home_usage}} (${{member.home_building_id}})`;
      document.getElementById('memberDest').textContent = `${{member.assigned_destination_usage || 'Extérieur / domicile'}} (${{member.assigned_destination_id}})`;
      document.getElementById('memberState').textContent = member.timeline_states[hour];
      document.getElementById('memberCurrent').textContent = member.timeline_labels[hour];
      renderTimeline(member);
      drawTrack(member, hour);
    }}

    function refresh() {{
      const role = roleSelect.value;
      renderProfileSummary(role);
      const member = selectedMember();
      const hour = Number(hourSlider.value);
      hourLabel.textContent = formatHour(hour);
      if (member) {{
        renderMemberPanel(member, hour);
      }}
    }}

    roleSelect.addEventListener('change', () => {{
      populateMemberSelect(roleSelect.value);
      refresh();
    }});
    memberSelect.addEventListener('change', refresh);
    hourSlider.addEventListener('input', refresh);

    buildRoleCards();
    populateRoleSelect();
    roleSelect.value = roleOrder[0];
    populateMemberSelect(roleOrder[0]);
    refresh();
  </script>
</body>
</html>
"""

    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(html_content, encoding="utf-8")
    return output_path
