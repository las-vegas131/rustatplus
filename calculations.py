# calculations.py
import pandas as pd
import numpy as np
from config import NEGATIVE_METRICS, METRIC_NAMES_RU, MATCH_METRIC_NAMES_RU

def get_position_group(pos):
    if not isinstance(pos, str):
        return 'CM'
    pos = pos.upper().strip()
    if pos in ['CF', 'FW', 'ST']: return 'FW'
    if pos in ['CAM', 'LAM', 'RAM', 'AM']: return 'AM'
    if pos in ['CDM', 'LCDM', 'RCDM', 'CM']: return 'CM'
    if pos in ['LD', 'RD', 'LWB', 'RWB']: return 'FB'
    if pos in ['CD', 'LCD', 'RCD', 'CB']: return 'CB'
    return 'CM'

def percentile_normalize(series):
    return series.fillna(0).rank(pct=True)

def format_metric_with_detail(metric, value, player_row):
    if metric == 'ttd_actions_p90':
        total = player_row.get('actions', 0)
        successful = player_row.get('actions_successful', 0)
        if total > 0:
            return f"{successful}/{total}"
        return ""
    if metric == 'ttd_opp_actions_p90':
        total = player_row.get('actions_opp_box', 0)
        successful = player_row.get('actions_opp_box_success', 0)
        if total > 0:
            return f"{successful}/{total}"
        return ""

    if metric.endswith('_pct') or metric == 'pass_accuracy':
        base_col = None
        if metric == 'pass_accuracy': base_col = 'passes'
        elif metric == 'dribbles_success_pct': base_col = 'dribbles'
        elif metric == 'tackles_success_pct': base_col = 'tackles'
        elif metric == 'challenges_won_pct': base_col = 'challenges'
        elif metric == 'air_challenges_won_pct': base_col = 'air_challenges'
        elif metric == 'crosses_accuracy': base_col = 'crosses'
        elif metric == 'progressive_passes_accuracy': base_col = 'progressive_passes'
        elif metric == 'passes_final_third_accuracy': base_col = 'passes_final_third'
        elif metric == 'short_passes_accuracy': base_col = 'short_passes'
        elif metric == 'long_passes_accuracy': base_col = 'long_passes'
        elif metric == 'passes_into_penalty_box_accuracy': base_col = 'passes_into_penalty_box'
        elif metric == 'super_long_passes_accuracy': base_col = 'super_long_passes'
        elif metric == 'dribbling_final_third_success_pct': base_col = 'dribbling_final_third'
        elif metric == 'defensive_challenges_won_pct': base_col = 'defensive_challenges'
        elif metric == 'attacking_challenges_won_pct': base_col = 'attacking_challenges'
        if base_col and base_col in player_row:
            total = player_row[base_col]
            if pd.notna(total) and total > 0:
                successful = int(round(total * value / 100))
                return f"{value:.1f}% ({successful}/{int(total)})"
        return f"{value:.1f}%"
    else:
        return f"{value:.2f}"

def format_match_metric(metric, value, player_row, league_avg=None, player_season_val=None):
    # Обработка ТТД метрик для матчей (они не в MATCH_ALL_METRICS, но могут быть добавлены)
    if metric == 'ttd_actions':
        total = player_row.get('actions', 0)
        succ = player_row.get('actions_successful', 0)
        if total > 0:
            main_str = f"{succ}/{total}"
        else:
            main_str = ""
    elif metric == 'ttd_opp_actions':
        total = player_row.get('actions_opp_box', 0)
        succ = player_row.get('actions_opp_box_success', 0)
        if total > 0:
            main_str = f"{succ}/{total}"
        else:
            main_str = ""
    else:
        if pd.isna(value):
            return "-"
        try:
            value = float(value)
        except (ValueError, TypeError):
            return str(value)

        main_str = f"{value:.2f}"

        if metric.endswith('_pct') or metric == 'pass_accuracy':
            base_col = None
            if metric == 'pass_accuracy': base_col = 'passes'
            elif metric == 'dribbles_success_pct': base_col = 'dribbles'
            elif metric == 'tackles_success_pct': base_col = 'tackles'
            elif metric == 'challenges_won_pct': base_col = 'challenges'
            elif metric == 'air_challenges_won_pct': base_col = 'air_challenges'
            elif metric == 'crosses_accuracy': base_col = 'crosses'
            elif metric == 'progressive_passes_accuracy': base_col = 'progressive_passes'
            elif metric == 'passes_final_third_accuracy': base_col = 'passes_final_third'
            elif metric == 'short_passes_accuracy': base_col = 'short_passes'
            elif metric == 'long_passes_accuracy': base_col = 'long_passes'
            elif metric == 'passes_into_penalty_box_accuracy': base_col = 'passes_into_penalty_box'
            elif metric == 'super_long_passes_accuracy': base_col = 'super_long_passes'
            elif metric == 'dribbling_final_third_success_pct': base_col = 'dribbling_final_third'
            elif metric == 'defensive_challenges_won_pct': base_col = 'defensive_challenges'
            elif metric == 'attacking_challenges_won_pct': base_col = 'attacking_challenges'
            elif metric == 'shots_on_target_pct': base_col = 'shots'
            if base_col and base_col in player_row:
                total = player_row[base_col]
                if pd.notna(total) and total > 0:
                    successful = int(round(total * value / 100))
                    main_str = f"{value:.1f}% ({successful}/{int(total)})"
                else:
                    main_str = f"{value:.1f}%"
            else:
                main_str = f"{value:.1f}%"
        else:
            accuracy_col = None
            if metric + '_accuracy' in player_row:
                accuracy_col = metric + '_accuracy'
            elif metric + '_success_pct' in player_row:
                accuracy_col = metric + '_success_pct'
            elif metric == 'shots' and 'shots_on_target' in player_row:
                shots_on_target = player_row.get('shots_on_target')
                if pd.notna(shots_on_target):
                    main_str = f"{int(shots_on_target)}/{int(value)}"
                else:
                    main_str = f"{value:.2f}"
            elif metric in ['goals', 'assists', 'xG', 'yellow_cards', 'red_cards',
                            'mistakes_goals', 'mistakes_chances', 'fouls', 'fouls_suffered']:
                main_str = f"{value:.2f}"
            else:
                if accuracy_col:
                    acc_val = player_row.get(accuracy_col)
                    total = value
                    if pd.notna(acc_val) and pd.notna(total) and total > 0:
                        if acc_val <= 100:
                            successful = int(round(total * acc_val / 100))
                        else:
                            successful = int(acc_val)
                        main_str = f"{successful}/{int(total)}"
                    else:
                        main_str = f"{int(value)}" if value == int(value) else f"{value:.2f}"
                else:
                    main_str = f"{int(value)}" if value == int(value) else f"{value:.2f}"

    # Стрелка сравнения с сезоном (только для числовых метрик, не для ТТД)
    if metric not in ['ttd_actions', 'ttd_opp_actions'] and player_season_val is not None and pd.notna(player_season_val):
        try:
            season_val = float(player_season_val)
            if not pd.isna(season_val):
                if metric in NEGATIVE_METRICS:
                    if value < season_val:
                        main_str += " (↑)"
                    elif value > season_val:
                        main_str += " (↓)"
                else:
                    if value > season_val:
                        main_str += " (↑)"
                    elif value < season_val:
                        main_str += " (↓)"
        except:
            pass

    # Цветные эмодзи для сравнения с лигой (только для числовых метрик)
    if metric not in ['ttd_actions', 'ttd_opp_actions'] and league_avg is not None and pd.notna(league_avg):
        try:
            avg = float(league_avg)
            if not pd.isna(avg):
                if metric in NEGATIVE_METRICS:
                    if value < avg:
                        prefix = '🔵 '
                    elif value > avg:
                        prefix = '🟤 '
                    else:
                        prefix = ''
                else:
                    if value > avg:
                        prefix = '🔵 '
                    elif value < avg:
                        prefix = '🟤 '
                    else:
                        prefix = ''
                return f'{prefix}{main_str}'
        except:
            pass

    return main_str

def calculate_ratings(df, position_weights, league_col='league'):
    if league_col in df.columns:
        result = []
        for _, grp in df.groupby(league_col):
            result.append(_calculate_ratings_for_group(grp, position_weights))
        return pd.concat(result, ignore_index=True)
    else:
        return _calculate_ratings_for_group(df, position_weights)

def _calculate_ratings_for_group(df, position_weights):
    all_used = set()
    for w in position_weights.values():
        for m, wgt in w.items():
            if wgt != 0:
                all_used.add(m)
    valid_metrics = [m for m in all_used if m in df.columns]
    if not valid_metrics:
        df['rating'] = 50.0
        return df

    norm_df = pd.DataFrame(index=df.index)
    for m in valid_metrics:
        norm_df[m] = percentile_normalize(df[m])
        if m in NEGATIVE_METRICS:
            norm_df[m] = 1 - norm_df[m]

    positions = df['position'].apply(get_position_group)
    ratings = pd.Series(0.5, index=df.index, dtype=float)

    for pos, weights in position_weights.items():
        mask = (positions == pos)
        if not mask.any():
            continue
        pos_metrics = [m for m, w in weights.items() if w != 0 and m in valid_metrics]
        if not pos_metrics:
            continue
        w_pos = np.array([weights[m] for m in pos_metrics])
        X = norm_df.loc[mask, pos_metrics].values
        pos_mask = w_pos > 0
        neg_mask = w_pos < 0
        pos_sum = (X[:, pos_mask] * w_pos[pos_mask]).sum(axis=1) if pos_mask.any() else np.zeros(len(X))
        pos_weight_sum = w_pos[pos_mask].sum() if pos_mask.any() else 0
        neg_sum = ((1 - X[:, neg_mask]) * (-w_pos[neg_mask])).sum(axis=1) if neg_mask.any() else np.zeros(len(X))
        neg_weight_sum = (-w_pos[neg_mask]).sum() if neg_mask.any() else 0
        pos_score = np.where(pos_weight_sum > 0, pos_sum / pos_weight_sum, 0.5)
        neg_score = np.where(neg_weight_sum > 0, neg_sum / neg_weight_sum, 0.5)
        rating = 100 * (pos_score + neg_score) / 2
        ratings[mask] = rating
    df['rating'] = ratings.round(1)
    return df

def calculate_match_ratings(df, position_weights, league_col='league'):
    if league_col in df.columns:
        result = []
        for _, grp in df.groupby(league_col):
            result.append(_calculate_match_ratings_for_group(grp, position_weights))
        return pd.concat(result, ignore_index=True)
    else:
        return _calculate_match_ratings_for_group(df, position_weights)

def _calculate_match_ratings_for_group(df, position_weights):
    all_used = set()
    for w in position_weights.values():
        for m, wgt in w.items():
            if wgt != 0:
                all_used.add(m)
    valid_metrics = [m for m in all_used if m in df.columns]
    if not valid_metrics:
        df['rating'] = 50.0
        return df
    norm_df = pd.DataFrame(index=df.index)
    for m in valid_metrics:
        norm_df[m] = percentile_normalize(df[m])
        if m in NEGATIVE_METRICS:
            norm_df[m] = 1 - norm_df[m]
    positions = df['position'].apply(get_position_group)
    ratings = pd.Series(0.5, index=df.index, dtype=float)
    for pos, weights in position_weights.items():
        mask = (positions == pos)
        if not mask.any():
            continue
        pos_metrics = [m for m, w in weights.items() if w != 0 and m in valid_metrics]
        if not pos_metrics:
            continue
        w_pos = np.array([weights[m] for m in pos_metrics])
        X = norm_df.loc[mask, pos_metrics].values
        pos_mask = w_pos > 0
        neg_mask = w_pos < 0
        pos_sum = (X[:, pos_mask] * w_pos[pos_mask]).sum(axis=1) if pos_mask.any() else np.zeros(len(X))
        pos_weight_sum = w_pos[pos_mask].sum() if pos_mask.any() else 0
        neg_sum = ((1 - X[:, neg_mask]) * (-w_pos[neg_mask])).sum(axis=1) if neg_mask.any() else np.zeros(len(X))
        neg_weight_sum = (-w_pos[neg_mask]).sum() if neg_mask.any() else 0
        pos_score = np.where(pos_weight_sum > 0, pos_sum / pos_weight_sum, 0.5)
        neg_score = np.where(neg_weight_sum > 0, neg_sum / neg_weight_sum, 0.5)
        rating = 100 * (pos_score + neg_score) / 2
        ratings[mask] = rating
    df['rating'] = ratings.round(1)
    return df

def build_position_tables(df, position_weights):
    tables = {}
    positions = ['FW', 'AM', 'CM', 'FB', 'CB']
    mandatory_metrics = ['ttd_actions_p90', 'ttd_opp_actions_p90']
    for pos in positions:
        pos_df = df[df['position'].map(get_position_group) == pos].copy()
        if pos_df.empty:
            tables[pos] = ([], [])
            continue
        metrics = [m for m, w in position_weights.get(pos, {}).items() if w != 0 and m in df.columns]
        # Добавляем обязательные ТТД, если они есть в данных
        for m in mandatory_metrics:
            if m in df.columns and m not in metrics:
                metrics.append(m)
        if not metrics:
            tables[pos] = ([], [])
            continue
        for m in metrics:
            col = pos_df[m]
            min_val, max_val = col.min(), col.max()
            if max_val - min_val == 0:
                pos_df[f'{m}_norm_pos'] = 0.5
            else:
                pos_df[f'{m}_norm_pos'] = (col - min_val) / (max_val - min_val)
            if m in NEGATIVE_METRICS:
                pos_df[f'{m}_norm_pos'] = 1.0 - pos_df[f'{m}_norm_pos']
        max_vals = {m: pos_df[f'{m}_norm_pos'].max() for m in metrics}
        min_vals = {m: pos_df[f'{m}_norm_pos'].min() for m in metrics}
        rows = []
        for _, player_row in pos_df.iterrows():
            row_data = [player_row['player'], int(player_row['minutes']), f"{player_row['rating']:.1f}"]
            for m in metrics:
                val = player_row[m]
                formatted = format_metric_with_detail(m, val, player_row)
                norm_val = player_row[f'{m}_norm_pos']
                is_max = (norm_val == max_vals[m])
                is_min = (norm_val == min_vals[m])
                if is_max and not is_min:
                    formatted = f"🟢 {formatted}"
                elif is_min and not is_max:
                    formatted = f"🔴 {formatted}"
                row_data.append(formatted)
            rows.append(row_data)
        headers = ['Игрок', 'Мин', 'Рейтинг'] + [METRIC_NAMES_RU.get(m, m) for m in metrics]
        tables[pos] = (rows, headers)
    return tables

def build_main_table(df, selected_metrics):
    mandatory_metrics = ['ttd_actions_p90', 'ttd_opp_actions_p90']
    metrics = [m for m in selected_metrics if m in df.columns]
    for m in mandatory_metrics:
        if m in df.columns and m not in metrics:
            metrics.append(m)
    if not metrics:
        return pd.DataFrame(columns=['№','Игрок','Поз','Мин','Рейтинг'])
    norm_cols = {}
    for m in metrics:
        col = df[m]
        min_val, max_val = col.min(), col.max()
        if max_val - min_val == 0:
            norm_cols[m] = pd.Series(0.5, index=df.index)
        else:
            norm_cols[m] = (col - min_val) / (max_val - min_val)
        if m in NEGATIVE_METRICS:
            norm_cols[m] = 1.0 - norm_cols[m]
    max_vals = {m: norm_cols[m].max() for m in metrics}
    min_vals = {m: norm_cols[m].min() for m in metrics}
    main_headers = ['№','Игрок','Поз','Мин','Рейтинг'] + [METRIC_NAMES_RU.get(m, m) for m in metrics]
    main_data = []
    for i, (_, row) in enumerate(df.iterrows(), start=1):
        row_data = [i, row['player'], row['position'], int(row['minutes']), f"{row['rating']:.1f}"]
        for m in metrics:
            val = row[m]
            detail = format_metric_with_detail(m, val, row)
            norm_val = norm_cols[m].loc[row.name]
            is_max = (norm_val == max_vals[m])
            is_min = (norm_val == min_vals[m])
            if is_max and not is_min:
                detail = f"🟢 {detail}"
            elif is_min and not is_max:
                detail = f"🔴 {detail}"
            row_data.append(detail)
        main_data.append(row_data)
    return pd.DataFrame(main_data, columns=main_headers)

def build_match_position_tables(df, position_weights, league_avg=None, player_season_map=None):
    tables = {}
    positions = ['FW', 'AM', 'CM', 'FB', 'CB']
    mandatory_metrics = ['ttd_actions', 'ttd_opp_actions']
    for pos in positions:
        pos_df = df[df['position'].map(get_position_group) == pos].copy()
        if pos_df.empty:
            tables[pos] = ([], [])
            continue
        metrics = [m for m, w in position_weights.get(pos, {}).items() if w != 0 and m in df.columns]
        # Добавляем ТТД метрики, если есть соответствующие поля
        if 'actions' in df.columns and 'actions_successful' in df.columns:
            if 'ttd_actions' not in metrics:
                metrics.append('ttd_actions')
        if 'actions_opp_box' in df.columns and 'actions_opp_box_success' in df.columns:
            if 'ttd_opp_actions' not in metrics:
                metrics.append('ttd_opp_actions')
        if not metrics:
            tables[pos] = ([], [])
            continue
        for m in metrics:
            if m not in pos_df.columns:
                continue
            col = pos_df[m]
            min_val, max_val = col.min(), col.max()
            if max_val - min_val == 0:
                pos_df[f'{m}_norm_pos'] = 0.5
            else:
                pos_df[f'{m}_norm_pos'] = (col - min_val) / (max_val - min_val)
            if m in NEGATIVE_METRICS:
                pos_df[f'{m}_norm_pos'] = 1.0 - pos_df[f'{m}_norm_pos']
        max_vals = {m: pos_df[f'{m}_norm_pos'].max() for m in metrics if m in pos_df.columns}
        min_vals = {m: pos_df[f'{m}_norm_pos'].min() for m in metrics if m in pos_df.columns}
        rows = []
        for _, player_row in pos_df.iterrows():
            player_name = player_row['player']
            row_data = [player_name, int(player_row['minutes']), f"{player_row['rating']:.1f}"]
            for m in metrics:
                if m not in player_row:
                    row_data.append('')
                    continue
                val = player_row[m]
                la = league_avg.get(m) if league_avg else None
                psv = None
                if player_season_map and player_name in player_season_map:
                    psv = player_season_map[player_name].get(m)
                formatted = format_match_metric(m, val, player_row, league_avg=la, player_season_val=psv)
                norm_val = player_row.get(f'{m}_norm_pos', 0.5)
                is_max = (norm_val == max_vals.get(m, -1))
                is_min = (norm_val == min_vals.get(m, 2))
                if is_max and not is_min:
                    formatted = f"🟢 {formatted}"
                elif is_min and not is_max:
                    formatted = f"🔴 {formatted}"
                row_data.append(formatted)
            rows.append(row_data)
        headers = ['Игрок', 'Мин', 'Рейтинг']
        for m in metrics:
            header = MATCH_METRIC_NAMES_RU.get(m, m)
            if league_avg and m in league_avg:
                avg_val = league_avg[m]
                if m.endswith('_pct') or m == 'pass_accuracy':
                    header += f"<br><small>(ср. {avg_val:.1f}%)</small>"
                else:
                    header += f"<br><small>(ср. {avg_val:.2f})</small>"
            headers.append(header)
        tables[pos] = (rows, headers)
    return tables

def build_match_main_table(df, selected_metrics, league_avg=None, player_season_map=None):
    mandatory_metrics = ['ttd_actions', 'ttd_opp_actions']
    metrics = [m for m in selected_metrics if m in df.columns]
    if 'actions' in df.columns and 'actions_successful' in df.columns:
        if 'ttd_actions' not in metrics:
            metrics.append('ttd_actions')
    if 'actions_opp_box' in df.columns and 'actions_opp_box_success' in df.columns:
        if 'ttd_opp_actions' not in metrics:
            metrics.append('ttd_opp_actions')
    if not metrics:
        return pd.DataFrame(columns=['№','Игрок','Поз','Мин','Рейтинг'])
    norm_cols = {}
    for m in metrics:
        col = df[m]
        min_val, max_val = col.min(), col.max()
        if max_val - min_val == 0:
            norm_cols[m] = pd.Series(0.5, index=df.index)
        else:
            norm_cols[m] = (col - min_val) / (max_val - min_val)
        if m in NEGATIVE_METRICS:
            norm_cols[m] = 1.0 - norm_cols[m]
    max_vals = {m: norm_cols[m].max() for m in metrics}
    min_vals = {m: norm_cols[m].min() for m in metrics}
    main_headers = ['№','Игрок','Поз','Мин','Рейтинг']
    for m in metrics:
        header = MATCH_METRIC_NAMES_RU.get(m, m)
        if league_avg and m in league_avg:
            avg_val = league_avg[m]
            if m.endswith('_pct') or m == 'pass_accuracy':
                header += f"<br><small>(ср. {avg_val:.1f}%)</small>"
            else:
                header += f"<br><small>(ср. {avg_val:.2f})</small>"
        main_headers.append(header)
    main_data = []
    for i, (_, row) in enumerate(df.iterrows(), start=1):
        player_name = row['player']
        row_data = [i, player_name, row['position'], int(row['minutes']), f"{row['rating']:.1f}"]
        for m in metrics:
            val = row[m]
            la = league_avg.get(m) if league_avg else None
            psv = None
            if player_season_map and player_name in player_season_map:
                psv = player_season_map[player_name].get(m)
            detail = format_match_metric(m, val, row, league_avg=la, player_season_val=psv)
            norm_val = norm_cols[m].loc[row.name]
            is_max = (norm_val == max_vals[m])
            is_min = (norm_val == min_vals[m])
            if is_max and not is_min:
                detail = f"🟢 {detail}"
            elif is_min and not is_max:
                detail = f"🔴 {detail}"
            row_data.append(detail)
        main_data.append(row_data)
    return pd.DataFrame(main_data, columns=main_headers)
