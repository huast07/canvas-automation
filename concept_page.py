#!/usr/bin/env python3
"""Render a source-linked, first-principles lesson as a local HTML page."""
import argparse
from datetime import datetime
from html import escape
import json
from pathlib import Path
import sys
import textwrap
import webbrowser

from study import course_dir, readiness, read_json


def require_text(value, label):
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f'{label} must be nonempty text')
    return value.strip()


def validate_graphic(graphic, label):
    if not isinstance(graphic, dict):
        raise ValueError(f'{label} requires an explanatory graphic')
    require_text(graphic.get('title'), f'{label} graphic title')
    require_text(graphic.get('caption'), f'{label} graphic caption')
    steps = graphic.get('steps')
    if not isinstance(steps, list) or not 2 <= len(steps) <= 8:
        raise ValueError(f'{label} graphic needs 2 to 8 steps')
    for step in steps:
        require_text(step, f'{label} graphic step')


def validate(data):
    if not isinstance(data, dict):
        raise ValueError('Lesson must be a JSON object')
    for field in ('course', 'exam', 'exam_id', 'overview'):
        require_text(data.get(field), field)
    knowledge = data.get('knowledge_map')
    if not isinstance(knowledge, list) or not knowledge:
        raise ValueError('Knowledge map needs at least one entry')
    for i, item in enumerate(knowledge, 1):
        if not isinstance(item, dict):
            raise ValueError(f'Knowledge map entry {i} must be an object')
        require_text(item.get('concept'), f'Knowledge map entry {i} concept')
        require_text(item.get('group'), f'Knowledge map entry {i} group')
        require_text(item.get('role'), f'Knowledge map entry {i} role')
        if not isinstance(item.get('prerequisites'), list):
            raise ValueError(f'Knowledge map entry {i} prerequisites must be a list')
        for prerequisite in item['prerequisites']:
            require_text(prerequisite, 'prerequisite')
    names = [item['concept'] for item in knowledge]
    if len(names) != len(set(names)):
        raise ValueError('Knowledge map concept names must be unique')
    for item in knowledge:
        for prerequisite in item['prerequisites']:
            if prerequisite not in names or prerequisite == item['concept']:
                raise ValueError('Each prerequisite must be a different concept on the knowledge map')
    relations = data.get('relationships', [])
    if not isinstance(relations, list):
        raise ValueError('relationships must be a list')
    for relation in relations:
        if not isinstance(relation, dict) or relation.get('from') not in names or relation.get('to') not in names or relation['from'] == relation['to']:
            raise ValueError('Relationships must connect different concepts on the knowledge map')
        require_text(relation.get('label'), 'Relationship label')
    lectures = data.get('lecture_explainers')
    if not isinstance(lectures, list) or not lectures:
        raise ValueError('At least one lecture explainer is required')
    for i, lecture in enumerate(lectures, 1):
        if not isinstance(lecture, dict):
            raise ValueError(f'Lecture explainer {i} must be an object')
        for field in ('lecture', 'concept', 'first_principles', 'derivation', 'example'):
            require_text(lecture.get(field), f'Lecture {i} {field}')
        if lecture['concept'] not in names:
            raise ValueError(f'Lecture {i} concept must appear on the knowledge map')
        validate_graphic(lecture.get('graphic'), f'Lecture {i}')
        if not isinstance(lecture.get('sources'), list) or not lecture['sources']:
            raise ValueError(f'Lecture {i} needs source citations')
        for source in lecture['sources']:
            require_text(source, f'Lecture {i} source')
    categories = data.get('categories')
    if not isinstance(categories, list) or not categories:
        raise ValueError('At least one question category is required')
    for i, category in enumerate(categories, 1):
        if not isinstance(category, dict):
            raise ValueError(f'Category {i} must be an object')
        require_text(category.get('title'), f'Category {i} title')
        require_text(category.get('purpose'), f'Category {i} purpose')
        concepts = category.get('concepts')
        if not isinstance(concepts, list) or not concepts:
            raise ValueError(f'Category {i} needs at least one concept')
        for j, concept in enumerate(concepts, 1):
            if not isinstance(concept, dict):
                raise ValueError(f'Category {i} concept {j} must be an object')
            for field in ('name', 'explanation', 'derivation'):
                require_text(concept.get(field), f'Category {i} concept {j} {field}')
            if concept['name'] not in names:
                raise ValueError(f'Category {i} concept {j} must appear on the knowledge map')
            sources = concept.get('sources')
            if not isinstance(sources, list) or not sources:
                raise ValueError(f'Category {i} concept {j} needs source citations')
            for source in sources:
                require_text(source, f'Category {i} concept {j} source')
        validate_graphic(category.get('graphic'), f'Category {i}')
        example = category.get('example')
        if not isinstance(example, dict):
            raise ValueError(f'Category {i} needs a worked example')
        require_text(example.get('problem'), f'Category {i} example problem')
        steps = example.get('steps')
        if not isinstance(steps, list) or not steps:
            raise ValueError(f'Category {i} example needs steps')
        for step in steps:
            require_text(step, f'Category {i} example step')
        progression = category.get('progression')
        if not isinstance(progression, dict):
            raise ValueError(f'Category {i} needs a progression')
        for stage in ('individual', 'combined'):
            require_text(progression.get(stage), f'Category {i} progression {stage}')
    gaps = data.get('gaps', [])
    if not isinstance(gaps, list):
        raise ValueError('gaps must be a list')
    for gap in gaps:
        require_text(gap, 'gap')
    return data


def text(value):
    return escape(str(value), quote=True).replace('\n', '<br>\n')


PALETTE = ['#d7edf1', '#f6e4bf', '#e4e3f5', '#d8efdf', '#f4dedc', '#dce8f7']


def svg_lines(label, x, y, max_width=22, max_lines=3):
    lines = textwrap.wrap(label, width=max_width, break_long_words=True, break_on_hyphens=False) or ['']
    if len(lines) > max_lines:
        lines = lines[:max_lines]
        lines[-1] = lines[-1][:max_width - 1] + '…'
    return ''.join(f'<tspan x="{x}" y="{y + i * 19}">{escape(line)}</tspan>' for i, line in enumerate(lines))


def render_mindmap(data):
    items = data['knowledge_map']
    groups = list(dict.fromkeys(item['group'] for item in items))
    group_index = {group: i for i, group in enumerate(groups)}
    ordered = [item for group in groups for item in items if item['group'] == group]
    positions = {item['concept']: (530, 48 + i * 86) for i, item in enumerate(ordered)}
    total_height = max(220, 70 + len(ordered) * 86)
    group_y = {}
    for group in groups:
        ys = [positions[item['concept']][1] + 30 for item in ordered if item['group'] == group]
        group_y[group] = sum(ys) / len(ys)
    center_y = total_height / 2
    branches, nodes, relations, relation_text = [], [], [], []
    for group in groups:
        gy = group_y[group]
        color = PALETTE[group_index[group] % len(PALETTE)]
        branches.append(f'<path class="branch" d="M 180 {center_y:.1f} C 200 {center_y:.1f}, 205 {gy:.1f}, 225 {gy:.1f}"/>')
        nodes.append(f'<rect x="225" y="{gy-30:.1f}" width="160" height="60" rx="12" fill="{color}" stroke="#9aabb8"/><title>{escape(group)}</title><text class="map-label" x="237" y="{gy-6:.1f}">{svg_lines(group, 237, gy-6, 17, 2)}</text>')
        for item in ordered:
            if item['group'] == group:
                x, y = positions[item['concept']]
                branches.append(f'<path class="branch" d="M 385 {gy:.1f} C 445 {gy:.1f}, 455 {y+30}, 530 {y+30}"/>')
    for index, item in enumerate(ordered):
        x, y = positions[item['concept']]
        color = PALETTE[group_index[item['group']] % len(PALETTE)]
        nodes.append(f'<a href="#concept-{index+1}"><title>{escape(item["concept"])} — {escape(item["group"])}</title><rect x="{x}" y="{y}" width="190" height="60" rx="12" fill="{color}" stroke="#9aabb8"/><text class="map-label" x="{x+12}" y="{y+25}">{svg_lines(item["concept"],x+12,y+25,20,2)}</text></a>')
    all_relations = [{'from': prerequisite, 'to': item['concept'], 'label': 'prerequisite for'} for item in items for prerequisite in item['prerequisites']]
    all_relations += data.get('relationships', [])
    for index, relation in enumerate(all_relations):
        _, y1 = positions[relation['from']]
        _, y2 = positions[relation['to']]
        curve = 755 + (index % 6) * 14
        relations.append(f'<path class="relation" d="M 720 {y1+30} C {curve} {y1+30}, {curve} {y2+30}, 720 {y2+30}" marker-end="url(#mind-arrow)"><title>{escape(relation["from"])} → {escape(relation["to"])}: {escape(relation["label"])}</title></path>')
        relation_text.append(f'<li><strong>{text(relation["from"])}</strong> — {text(relation["label"])} → <strong>{text(relation["to"])}</strong></li>')
    center = f'<rect x="20" y="{center_y-38:.1f}" width="160" height="76" rx="14" fill="#143249"/><text fill="white" font-size="14" font-weight="700" x="32" y="{center_y-8:.1f}">{svg_lines(data["course"],32,center_y-8,17,2)}</text>'
    svg = f'<div class="diagram-scroll" tabindex="0" aria-label="Scrollable knowledge mind map"><svg viewBox="0 0 860 {total_height}" role="img" aria-label="Knowledge mind map: course branches to concept groups; dashed arrows show concept relationships"><defs><marker id="mind-arrow" markerWidth="8" markerHeight="8" refX="7" refY="4" orient="auto"><path d="M0 0 L8 4 L0 8 Z" fill="#b45c27"/></marker></defs>{"".join(branches)}{"".join(relations)}{center}{"".join(nodes)}</svg></div>'
    legend = ''.join(f'<span><i style="background:{PALETTE[i % len(PALETTE)]}"></i>{text(group)}</span>' for i, group in enumerate(groups))
    relation_list = ''.join(relation_text) or '<li>No relationships were recorded.</li>'
    return svg + f'<div class="legend">{legend}</div><details open><summary>Concept relationships</summary><ul>{relation_list}</ul></details>'


def render_graphic(graphic, identifier):
    steps = graphic['steps']
    rows = [textwrap.wrap(step, width=50, break_long_words=True) or [''] for step in steps]
    positions, y = [], 20
    for row in rows:
        height = max(58, 25 + 20 * len(row))
        positions.append((y, height))
        y += height + 30
    elements = []
    for index, (step, row) in enumerate(zip(steps, rows)):
        top, height = positions[index]
        elements.append(f'<rect x="20" y="{top}" width="660" height="{height}" rx="10" fill="#e5f1f3" stroke="#8eb9c0"/><title>{escape(step)}</title><text class="map-label" x="36" y="{top+27}">{svg_lines(step,36,top+27,50,len(row))}</text>')
        if index < len(rows)-1:
            elements.append(f'<path d="M 350 {top+height} V {positions[index+1][0]-5}" stroke="#367887" stroke-width="2" fill="none" marker-end="url(#{identifier}-arrow)"/>')
    return f'<figure class="explain-graphic"><figcaption><strong>{text(graphic["title"])}</strong><br>{text(graphic["caption"])}</figcaption><svg viewBox="0 0 700 {y-10}" role="img" aria-label="{escape(graphic["title"], quote=True)}: {escape(graphic["caption"], quote=True)}"><defs><marker id="{identifier}-arrow" markerWidth="8" markerHeight="8" refX="7" refY="4" orient="auto"><path d="M0 0 L8 4 L0 8 Z" fill="#367887"/></marker></defs>{"".join(elements)}</svg><ol class="sr-only">{"".join(f"<li>{text(step)}</li>" for step in steps)}</ol></figure>'


def render(data):
    validate(data)
    nav = ''.join(f'<li><a href="#category-{i}">{text(cat["title"])}</a></li>' for i, cat in enumerate(data['categories'], 1))
    diagram = render_mindmap(data)
    knowledge = []
    for index, item in enumerate([item for group in dict.fromkeys(x['group'] for x in data['knowledge_map']) for item in data['knowledge_map'] if item['group'] == group], 1):
        prereqs = ', '.join(item['prerequisites']) if item['prerequisites'] else 'None listed'
        knowledge.append(f'<article id="concept-{index}" class="map-card"><p class="eyebrow">{text(item["group"])}</p><h3>{text(item["concept"])}</h3><p>{text(item["role"])}</p><p class="sources"><strong>Builds on:</strong> {text(prereqs)}</p></article>')
    lectures = []
    for index, lecture in enumerate(data['lecture_explainers'], 1):
        refs = ''.join(f'<li>{text(source)}</li>' for source in lecture['sources'])
        lectures.append(f'<article class="concept"><p class="eyebrow">{text(lecture["lecture"])}</p><h3>{text(lecture["concept"])}</h3><p>{text(lecture["first_principles"])}</p><p><strong>Reasoning / derivation.</strong> {text(lecture["derivation"])}</p><p><strong>Example.</strong> {text(lecture["example"])}</p>{render_graphic(lecture["graphic"], f"lecture-{index}")}<div class="sources"><strong>Sources</strong><ul>{refs}</ul></div></article>')
    sections = []
    for i, category in enumerate(data['categories'], 1):
        concepts = []
        for concept in category['concepts']:
            sources = ''.join(f'<li>{text(source)}</li>' for source in concept['sources'])
            concepts.append(f'<article class="concept"><h3>{text(concept["name"])}</h3><p>{text(concept["explanation"])}</p><p><strong>Reasoning / derivation.</strong> {text(concept["derivation"])}</p><div class="sources"><strong>Sources</strong><ul>{sources}</ul></div></article>')
        example = category['example']
        steps = ''.join(f'<li>{text(step)}</li>' for step in example['steps'])
        progression = category['progression']
        sections.append(f'''<section id="category-{i}" class="category"><p class="eyebrow">QUESTION CATEGORY {i:02}</p><h2>{text(category['title'])}</h2><p class="lead">{text(category['purpose'])}</p><div class="concept-list">{''.join(concepts)}</div>{render_graphic(category['graphic'], f'category-{i}')}<div class="example"><h3>Worked example</h3><p>{text(example['problem'])}</p><ol>{steps}</ol></div><div class="progression"><h3>Practice progression</h3><p><strong>Start with one concept.</strong> {text(progression['individual'])}</p><p><strong>Combine concepts.</strong> {text(progression['combined'])}</p></div></section>''')
    gaps = ''.join(f'<li>{text(gap)}</li>' for gap in data.get('gaps', [])) or '<li>No additional gaps were recorded; verify the source inventory.</li>'
    return f'''<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><meta name="referrer" content="no-referrer"><title>{text(data['course'])} — exam concepts</title>
<style>
:root{{--ink:#17263b;--muted:#52657a;--line:#dce5ed;--blue:#095d75;--paper:#fff;--bg:#f3f6f8}}*{{box-sizing:border-box}}html{{scroll-behavior:smooth}}body{{margin:0;background:var(--bg);color:var(--ink);font:16px/1.65 -apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif}}a{{color:#075c78}}a:focus-visible{{outline:3px solid #d98520;outline-offset:3px}}header{{background:#143249;color:white;padding:3.5rem max(1.25rem,calc((100vw - 1120px)/2));}}header p{{max-width:65ch;margin:.7rem 0 0;color:#d4e6eb}}h1{{font-size:clamp(2rem,5vw,3.2rem);line-height:1.12;margin:.35rem 0}}.eyebrow{{font-size:.72rem;font-weight:750;letter-spacing:.13em;text-transform:uppercase;color:#357387}}header .eyebrow{{color:#94d8df}}.layout{{max-width:1120px;margin:auto;padding:2rem 1.25rem 4rem;display:grid;grid-template-columns:240px minmax(0,1fr);gap:2rem;align-items:start}}nav{{position:sticky;top:1.2rem;background:var(--paper);border:1px solid var(--line);border-radius:12px;padding:1.2rem}}nav h2{{font-size:.85rem;margin:0}}.diagram-scroll{{overflow-x:auto;border:1px solid var(--line);border-radius:10px;background:#fbfcfd}}.diagram-scroll svg{{display:block;min-width:760px;width:100%;height:auto}}.branch{{fill:none;stroke:#afc3ca;stroke-width:1.5}}.relation{{fill:none;stroke:#b45c27;stroke-width:2;stroke-dasharray:5 3}}.map-label{{fill:#17263b;font:600 14px -apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif}}.legend{{display:flex;gap:.8rem;flex-wrap:wrap;margin:1rem 0;font-size:.86rem}}.legend i{{display:inline-block;width:.8rem;height:.8rem;border:1px solid #9aabb8;border-radius:3px;margin-right:.3rem}}.explain-graphic{{margin:1.25rem 0;padding:1rem;border:1px solid var(--line);border-radius:10px}}.explain-graphic svg{{width:100%;height:auto;display:block}}.sr-only{{position:absolute;width:1px;height:1px;padding:0;margin:-1px;overflow:hidden;clip:rect(0,0,0,0);white-space:nowrap;border:0}}.map-grid{{display:grid;grid-template-columns:repeat(auto-fit,minmax(190px,1fr));gap:.75rem}}.map-card{{padding:1rem;border-radius:10px;background:#f1f7f8}}.map-card p{{font-size:.92rem}}nav ol{{padding-left:1.3rem;margin:.6rem 0}}nav li{{margin:.45rem 0}}main{{min-width:0}}.category,.notice{{background:var(--paper);border:1px solid var(--line);border-radius:14px;padding:clamp(1.3rem,3vw,2rem);margin-bottom:1.2rem}}h2{{font-size:1.65rem;line-height:1.25;margin:.25rem 0 .7rem}}h3{{font-size:1.05rem;margin:0 0 .5rem}}p{{margin:.5rem 0 1rem;overflow-wrap:anywhere}}.lead{{color:var(--muted);font-size:1.05rem}}.concept{{border-left:3px solid #62a7b1;padding:.15rem 0 .15rem 1rem;margin:1.5rem 0}}.sources{{font-size:.88rem;color:var(--muted);overflow-wrap:anywhere}}.sources ul{{margin:.2rem 0;padding-left:1.1rem}}.example,.progression{{padding:1.2rem;border-radius:10px;background:#f1f7f8;margin-top:1rem}}.progression{{background:#fbf5ea}}.example ol{{padding-left:1.4rem}}.example li{{margin:.5rem 0}}.notice{{color:var(--muted);font-size:.92rem}}@media(max-width:700px){{header{{padding:2rem 1.25rem}}.layout{{display:block}}nav{{position:static;margin-bottom:1rem}}}}@media print{{body{{background:white}}header{{padding:1rem;background:white;color:black}}header p,header .eyebrow{{color:black}}.layout{{display:block;padding:0}}nav{{position:static}}.category,.notice{{break-inside:avoid;border:0}}}}
</style></head><body><header><p class="eyebrow">FIRST PRINCIPLES • EXAM PREPARATION</p><h1>{text(data['course'])}</h1><p>{text(data['exam'])}</p><p>{text(data['overview'])}</p></header><div class="layout"><nav aria-label="Lesson contents"><h2>On this page</h2><ul><li><a href="#knowledge-map">Knowledge map</a></li><li><a href="#problem-types">Problem types and concepts</a></li><li><a href="#lecture-explainers">Lecture explainers</a></li></ul><h2>Problem categories</h2><ol>{nav}</ol><a href="#gaps">Coverage and gaps</a></nav><main><section id="knowledge-map" class="category"><p class="eyebrow">01 • THE BIG PICTURE</p><h2>Knowledge map</h2><p class="lead">Key concepts and their prerequisite relationships.</p>{diagram}<p class="sources">Colored branches group concepts. Dashed arrows show relationships; use the list above for their labels.</p><div class="map-grid">{''.join(knowledge)}</div></section><section id="problem-types" class="notice"><h2>Concepts for each problem type</h2><p>The categories below connect each question type to its prerequisites, worked example and practice progression.</p></section>{''.join(sections)}<section id="lecture-explainers" class="category"><p class="eyebrow">03 • BUILD FROM FIRST PRINCIPLES</p><h2>Core lecture concepts</h2><p class="lead">Definitions, reasoning and examples organized by lecture.</p>{''.join(lectures)}</section><section id="gaps" class="notice"><h2>Coverage and gaps</h2><ul>{gaps}</ul><p>Explanations are study aids. Verify formulas, quotations, diagrams and exam requirements against the cited sources.</p></section></main></div></body></html>'''


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('course_id', type=int)
    parser.add_argument('lesson', type=Path, help='UTF-8 lesson JSON built from course sources')
    parser.add_argument('--open', action='store_true', dest='open_page', help='Open the finished local page in your browser')
    args = parser.parse_args()
    try:
        missing, warnings = readiness(args.course_id)
        if missing:
            raise ValueError('Required first: ' + ', '.join(missing))
        for warning in warnings:
            print('Warning:', warning, file=sys.stderr)
        data = json.loads(args.lesson.read_text(encoding='utf-8'))
        validate(data)
        scope = read_json(course_dir(args.course_id) / 'exam-scope.json', {})
        if data['exam_id'] != (scope.get('exam_id') or scope.get('exam')):
            raise ValueError('Lesson exam_id must match the saved exam scope')
        html = render(data)
        directory = course_dir(args.course_id) / 'lessons'
        directory.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now().strftime('%Y%m%d-%H%M%S')
        for attempt in range(1000):
            suffix = '' if attempt == 0 else f'-{attempt}'
            path = directory / f'concepts-{stamp}{suffix}.html'
            try:
                with path.open('x', encoding='utf-8') as out:
                    out.write(html)
                break
            except FileExistsError:
                continue
        else:
            raise ValueError('Could not allocate a new lesson file')
        print(f'Lesson saved: {path.resolve()}')
        if args.open_page:
            if not webbrowser.open(path.resolve().as_uri()):
                print('Could not open the browser automatically; open the saved file manually.', file=sys.stderr)
                return 1
            print('Browser launch requested.')
        return 0
    except (ValueError, OSError, json.JSONDecodeError) as exc:
        print(f'Error: {exc}', file=sys.stderr)
        return 1


if __name__ == '__main__':
    sys.exit(main())
