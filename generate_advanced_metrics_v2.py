import json
import os
import glob
import datetime

# Cross-source canonical name map — applied BEFORE fuzzy normalization.
# Resolves cases where API and Proballers use different names for the same club,
# which would otherwise create two separate ghost entries in the matrix.
# Key = API name, Value = Proballers (canonical) name.
CROSS_SOURCE_CANONICAL_MAP = {
    # Portugal Proliga (261)
    "Vasco Da Gama":       "SC Vasco da Gama",
    "SC Vasco Da Gama":    "SC Vasco da Gama",
    # Iceland Premier League
    "KR Basket":           "KR Reykjavik",
    # Poland Energa Basket Liga (72)
    "Dabrowa Gornicza":    "MKS Dąbrowa Górnicza",
    "Zielona Gora":        "Enea Zastal Zielona Góra",
    "Torun":               "Twarde Pierniki Toruń",
    "Gornik Walbrzych":    "Górnik Trans.eu Walbrzych",
    "Ostrow Wielkopolski": "Stal Ostrów Wielkopolski",
    # European / International Title Sponsor & Rebranding Aliases (2026-27)
    # --- Euroleague (120) — merge Proballers full names → Flashscore/API canonical ---
    "Crvena Zvezda Belgrade":      "Crvena Zvezda Meridianbet",
    "Partizan Belgrade":           "Partizan Mozzart Bet",
    "EA7 Emporio Armani Milan":    "Olimpia Milano",
    "Armani Olimpia Milan":        "Olimpia Milano",
    "LDLC ASVEL":                  "Lyon-Villeurbanne",
    "FC Barcelona":                "Barcelona",
    "FC Bayern Munich":            "Bayern",
    "AS Monaco":                   "Monaco",
    "Valencia Basket":             "Valencia",
    "Fenerbahce Istanbul":         "Fenerbahce",
    "Olympiacos Piraeus":          "Olympiacos",
    "Olympiacos SFP":              "Olympiacos",
    "Panathinaikos Athens":        "Panathinaikos",
    "Anadolu Efes Istanbul":       "Anadolu Efes",
    "Maccabi Playtika Tel Aviv":   "Maccabi Tel Aviv",
    "Maccabi Rapyd Tel Aviv":      "Maccabi Tel Aviv",
    "Baskonia Vitoria-Gasteiz":    "Baskonia",
    "Dubai Basketball":            "Dubai",
    "Virtus Segafredo Bologna":    "Virtus Bologna",
    "Besiktas Istanbul":           "Besiktas",
    "Besiktas S.J.":               "Besiktas",
    "Hapoel Tel-Aviv":             "Hapoel Tel Aviv",
    "A++ Massagno":                "Spinelli Massagno",
    "CityX Mons-Hainaut":          "Union Mons-Hainaut",
    "ZZ Rotterdam City":           "Rotterdam City Basketball",
    "Patrioti Levice":             "Levickí Patrioti",
    "Sabios Baloncesto":           "Sabios de Manizales",
    "Unicaja":             "Unicaja Malaga",
    "Unics Kazan":         "UNICS Kazan",
    "Ulm":                 "Ratiopharm Ulm",
    "Utsunomiya Brex":     "Utsunomiya",
    "Vaerlose":            "Vaerlose Blue Hawks",
    "Sopron KC":           "Soproni KC",
    "Soproni KC":          "Sopron KC",
    # Australia NBL1 (Official Sportradar -> API Basketball)
    "Hobart":                      "Hobart Chargers",
    "Southern Districts":          "Southern District Spartans",
    "Southern District":           "Southern District Spartans",
    "SW Slammers":                 "South West Slammers",
    "SW Metro":                    "South West Metro Pirates",
    "Albury Wodonga":              "Albury-Wodonga Bandits",
    "Albury W":                    "Albury-Wodonga Bandits",
    "Manly Warringah":             "Manly Warringah Sea Eagles",
    "Manly W.":                    "Manly Warringah Sea Eagles",
    "Manly W. W":                  "Manly Warringah Sea Eagles",
    "Hornsby KuRingGai":           "Hornsby Ku-Ring-Gai Spiders",
    "Hornsby S.":                  "Hornsby Ku-Ring-Gai Spiders",
    "Hornsby S. W":                "Hornsby Ku-Ring-Gai Spiders",
    "Northern Force":              "Northern Tasmania",
    "Eastern Suns":                "Kalamunda Eastern Suns",
    "Brisbane":                    "Brisbane Capitals",
    "Gold Coast":                  "Gold Coast Rollers",
    "North Adelaide":              "North Adelaide Rockets",
    "Central Districts":           "Central District Lions",
    "Sunshine Coast":              "Sunshine Coast Phoenix",
    "North Gold Coast":            "North Gold Coast Seahawks",
    "Beeliar Boodjar":             "Cockburn Cougars",
    "Cockburn Cougars":            "Cockburn Cougars",
    "Mandurah Magic":              "Mandurah Magic",
    "Warwick Senators":            "Warwick Senators",
    "Willetton Tigers":            "Willetton Tigers",
    "Lakeside Lightning":          "Lakeside Lightning",
    "Perry Lakes Hawks":           "Perry Lakes Hawks",
    "Rockingham Flames":           "Rockingham Flames",
    "Joondalup Wolves":            "Joondalup Wolves",
    "Geraldton Buccaneers":        "Geraldton Buccaneers",
    "Goldfields Giants":           "Goldfields Giants",
    "Perth Redbacks":              "Perth Redbacks",
    "East Perth Eagles":           "East Perth Eagles",
    "Forestville":                 "Forestville Eagles",
    "Sturt":                       "Sturt Sabres",
    "Mavericks":                   "Eastern Mavericks",
    "Norths":                      "Norths Bears",
    "Sutherland":                  "Sutherland Sharks",
    "Sydney":                      "Sydney Comets",
    "Penrith":                     "Penrith Panthers",
    "Penrith P.":                  "Penrith Panthers",
    "Penrith P. W":                "Penrith Panthers",
    "Maitland":                    "Maitland Mustangs",
    "Maitland M.":                  "Maitland Mustangs",
    "Hills":                       "Hills Hornets",
    # NBL1 South (209/210)
    "Nunawading Spectres":         "Nunawading Spectres",
    "Frankston Blues":             "Frankston Blues",
    "Geelong United":              "Geelong United",
    "Kilsyth Cobras":              "Kilsyth Cobras",
    "Ballarat Miners":             "Ballarat Miners",
    "Dandenong Rangers":           "Dandenong Rangers",
    "Diamond Valley Eagles":       "Diamond Valley Eagles",
    "Eltham Wildcats":             "Eltham Wildcats",
    "Knox Raiders":                "Knox Raiders",
    "Ringwood Hawks":              "Ringwood Hawks",
    "Waverley Falcons":            "Waverley Falcons",
    # --- Australia NBL1 West (214) ---
    "Cockburn":                    "Cockburn Cougars",
    "East Perth":                  "East Perth Eagles",
    "Eastern Suns":                "Kalamunda Eastern Suns",
    "Geraldton":                   "Geraldton Buccaneers",
    "Goldfields":                  "Goldfields Giants",
    "Joondalup":                   "Joondalup Wolves",
    "Lakeside":                    "Lakeside Lightning",
    "Mandurah":                    "Mandurah Magic",
    "Perry Lakes":                 "Perry Lakes Hawks",
    "Perth":                       "Perth Redbacks",
    "Rockingham":                  "Rockingham Flames",
    "SW Slammers":                 "South West Slammers",
    "Warwick":                     "Warwick Senators",
    "Willetton":                   "Willetton Tigers",
    # --- Belgium Pro Basketball League (374) ---
    "Antwerp Giants":              "Windrose Giants Antwerp",
    "Spirou Charleroi":            "Spirou Basket",
    "Oostende":                    "Filou Oostende",
    "Mechelen":                    "Kangoeroes",
    "Okapi Aalst":                 "Okapi Aalstar",
    "Limburg":                     "Limburg United",
    "Mons-Hainaut":                "Union Mons-Hainaut",
    "Liege":                       "Liege Basket",
    # --- Netherlands DBL (65) ---
    "Den Helder":                  "Den Helder Suns",
    "Zwolle":                      "Landstede Hammers",
    "Leiden":                      "ZZ Leiden",
    "BAL Weert":                   "PrismaWorx BAL",
    "Rotterdam":                   "Rotterdam City Basketball",
    "Den Bosch":                   "Heroes Den Bosch",
}

def calculate_iterative_srs(games):
    """
    Computes a mathematically pure Simple Rating System (SRS) manually via recursive iteration.
    This safely avoids immense Python library overheads while guaranteeing perfect matrix calibration.
    """
    import math
    import datetime
    teams = {}
    
    if not games: return teams
        
    # Get the "current" date relative to the dataset
    max_date = max((g.get("_parsed_date", datetime.datetime.min) for g in games), default=datetime.datetime.now())
    if max_date == datetime.datetime.min:
        max_date = datetime.datetime.now()
    
    # 1. Build Base Profiles
    for g in games:
        ht = g.get("home_team")
        at = g.get("away_team")
        hs = g.get("home_score", 0)
        as_ = g.get("away_score", 0)
        
        if not ht or not at or not hs or not as_:
            continue
            
        g_date = g.get("_parsed_date", max_date)
        if g_date == datetime.datetime.min: 
            g_date = max_date
            
        days_old = (max_date - g_date).days
        
        # Time Decay: 14-day plateau, λ=0.030.
        # Prior season games during early-season transition receive a constant anchor weight (0.35)
        # so the summer vacation gap does not decay them to zero.
        if g.get("is_prior_season"):
            weight = 0.35
        else:
            weight = 1.0
            if days_old > 14:
                weight = math.exp(-0.030 * (days_old - 14))
            if weight < 0.01:
                continue  # Hard cutoff — game too old to contribute meaningfully
        
        if ht not in teams:
            teams[ht] = {"games": 0, "weight_sum": 0.0, "wins": 0, "pts_for": 0, "pts_against": 0, "scaled_margin_sum": 0.0, "opponents": [], "game_totals": []}
        if at not in teams:
            teams[at] = {"games": 0, "weight_sum": 0.0, "wins": 0, "pts_for": 0, "pts_against": 0, "scaled_margin_sum": 0.0, "opponents": [], "game_totals": []}
            
        raw_margin = hs - as_
        
        # True HCA Stripping: Subtract 2.5 from home team's margin
        ht_margin = raw_margin - 2.5
        at_margin = -raw_margin + 2.5
        
        # Logarithmic Blowout Scaling
        def scale_margin(m):
            sign = 1 if m >= 0 else -1
            abs_m = abs(m)
            if abs_m <= 12: return float(m)
            return sign * (12.0 + 4.0 * math.log(abs_m - 11.0))
            
        ht_scaled_margin = scale_margin(ht_margin)
        at_scaled_margin = scale_margin(at_margin)
        
        teams[ht]["games"] += 1
        teams[ht]["weight_sum"] += weight
        teams[ht]["pts_for"] += (hs * weight)
        teams[ht]["pts_against"] += (as_ * weight)
        teams[ht]["scaled_margin_sum"] += (ht_scaled_margin * weight)
        teams[ht]["opponents"].append((at, weight))
        teams[ht]["game_totals"].append(hs + as_)
        if hs > as_: teams[ht]["wins"] += 1
        
        teams[at]["games"] += 1
        teams[at]["weight_sum"] += weight
        teams[at]["pts_for"] += (as_ * weight)
        teams[at]["pts_against"] += (hs * weight)
        teams[at]["scaled_margin_sum"] += (at_scaled_margin * weight)
        teams[at]["opponents"].append((ht, weight))
        teams[at]["game_totals"].append(hs + as_)
        if as_ > hs: teams[at]["wins"] += 1
        
    for t, data in teams.items():
        if data["weight_sum"] > 0:
            data["raw_margin"] = data["scaled_margin_sum"] / data["weight_sum"]
            data["srs"] = data["raw_margin"]
        else:
            data["raw_margin"] = 0.0
            data["srs"] = 0.0
            
    # Convergence Matrix Loop
    for _ in range(30):
        max_delta = 0.0
        for t, data in teams.items():
            if data["weight_sum"] == 0: continue
            old_srs = data["srs"]
            sos_sum = sum(teams[opp_name]["srs"] * opp_weight for opp_name, opp_weight in data["opponents"])
            data["srs"] = data["raw_margin"] + (sos_sum / data["weight_sum"])
            max_delta = max(max_delta, abs(data["srs"] - old_srs))
        if max_delta < 0.001: break

    # Store explicit Strength of Schedule (SOS) for each team
    for t, data in teams.items():
        if data["weight_sum"] > 0:
            sos_sum = sum(teams[opp_name]["srs"] * opp_weight for opp_name, opp_weight in data["opponents"])
            data["sos"] = sos_sum / data["weight_sum"]
        else:
            data["sos"] = 0.0
            
    return teams


def calculate_advanced_ratings(games, pace_pivot=76.0, eff_pivot=108.0):
    """
    Compute true KenPom/Barttorvik-equivalent Opponent-Adjusted Efficiency ratings (AdjO & AdjD)
    with Gauss-Seidel iterative solver, decaying Bayesian prior anchor,
    and Dean Oliver's Four Factors.
    """
    import math
    import datetime
    teams = {}
    if not games: return []
    
    max_date = max((g.get("_parsed_date", datetime.datetime.min) for g in games), default=datetime.datetime.now())
    if max_date == datetime.datetime.min: max_date = datetime.datetime.now()

    def get_poss(t_s, o_s, pace_p):
        if t_s and o_s:
            fga = t_s.get("FGA", 0) + o_s.get("FGA", 0)
            fta = t_s.get("FTA", 0) + o_s.get("FTA", 0)
            tov = t_s.get("TOV", 0) + o_s.get("TOV", 0)
            orb = t_s.get("ORB", 0) + o_s.get("ORB", 0)
            poss = 0.5 * (fga - orb + tov + 0.44 * fta)
            if 40 <= poss <= 100:
                return poss, True
        return pace_p, False

    # PASS 1: Build schedules and extract Four Factors
    for g in games:
        ht = CROSS_SOURCE_CANONICAL_MAP.get(g.get("home_team"), g.get("home_team"))
        at = CROSS_SOURCE_CANONICAL_MAP.get(g.get("away_team"), g.get("away_team"))
        hs = g.get("home_score", 0)
        as_ = g.get("away_score", 0)
        if not ht or not at or hs <= 0 or as_ <= 0:
            continue

        g_date = g.get("_parsed_date", max_date)
        if g_date == datetime.datetime.min: g_date = max_date
        days_old = (max_date - g_date).days

        if g.get("is_prior_season"):
            weight = 0.35
        else:
            weight = 1.0 if days_old <= 14 else math.exp(-0.030 * (days_old - 14))
            if weight < 0.01: continue

        st = g.get("stats") or g.get("advanced_stats") or {}
        home_s = st.get("home", {}) if isinstance(st, dict) else {}
        away_s = st.get("away", {}) if isinstance(st, dict) else {}
        poss, has_box_poss = get_poss(home_s, away_s, pace_pivot)

        # Raw possession efficiencies (pts per 100 poss)
        h_eff = (hs / poss) * 100.0
        a_eff = (as_ / poss) * 100.0

        # Neutral-site normalization (HCA ~ 1.75 pts per 100 poss)
        hca_eff = 1.75
        h_eff_n = h_eff - hca_eff
        a_eff_n = a_eff + hca_eff

        for team, opp, pts, opp_pts, off_eff, def_eff, t_s, o_s, is_home in [
            (ht, at, hs, as_, h_eff_n, a_eff_n, home_s, away_s, True),
            (at, ht, as_, hs, a_eff_n, h_eff_n, away_s, home_s, False),
        ]:
            if team not in teams:
                teams[team] = {
                    "games": 0, "curr_games": 0, "weight_sum": 0.0, "wins": 0,
                    "pts_for": 0, "pts_against": 0, "game_totals": [],
                    "schedule": [], "sum_off_eff": 0.0, "sum_def_eff": 0.0,
                    "poss_sum": 0.0, "poss_weight": 0.0, "poss_games": 0, "poss_schedule": [],
                    # Four Factors accumulators
                    "box_weight": 0.0, "fga": 0, "fta": 0, "tov": 0, "orb": 0, "drb": 0, "trb": 0,
                    "opp_fga": 0, "opp_fta": 0, "opp_pts": 0, "opp_tov": 0, "opp_orb": 0,
                }
            td = teams[team]
            td["games"] += 1
            if not g.get("is_prior_season"):
                td["curr_games"] += 1
            td["weight_sum"] += weight
            td["pts_for"] += (pts * weight)
            td["pts_against"] += (opp_pts * weight)
            td["sum_off_eff"] += (off_eff * weight)
            td["sum_def_eff"] += (def_eff * weight)
            td["game_totals"].append(pts + opp_pts)
            td["schedule"].append((opp, off_eff, def_eff, weight))
            if has_box_poss:
                td["poss_sum"] += (poss * weight)
                td["poss_weight"] += weight
                td["poss_games"] += 1
                td["poss_schedule"].append((opp, poss, weight))
            if pts > opp_pts:
                td["wins"] += 1

            if t_s and o_s:
                td["box_weight"] += weight
                def get_stat(s_dict, key):
                    return s_dict.get(key.upper(), s_dict.get(key.lower(), 0))
                td["fga"] += (get_stat(t_s, "FGA") * weight)
                td["fta"] += (get_stat(t_s, "FTA") * weight)
                td["tov"] += (get_stat(t_s, "TOV") * weight)
                td["orb"] += (get_stat(t_s, "ORB") * weight)
                t_drb = get_stat(t_s, "DRB")
                t_trb = get_stat(t_s, "TRB")
                t_orb = get_stat(t_s, "ORB")
                if not t_drb and t_trb:
                    t_drb = max(0, t_trb - t_orb)
                td["drb"] += (t_drb * weight)
                td["trb"] += (t_trb * weight)
                td["opp_fga"] += (get_stat(o_s, "FGA") * weight)
                td["opp_fta"] += (get_stat(o_s, "FTA") * weight)
                td["opp_pts"] += (opp_pts * weight)
                td["opp_tov"] += (get_stat(o_s, "TOV") * weight)
                td["opp_orb"] += (get_stat(o_s, "ORB") * weight)

    if not teams:
        return []

    # Initialize ratings with raw neutral efficiencies and box-score tempo
    for td in teams.values():
        if td["weight_sum"] > 0:
            td["raw_off"] = td["sum_off_eff"] / td["weight_sum"]
            td["raw_def"] = td["sum_def_eff"] / td["weight_sum"]
        else:
            td["raw_off"] = eff_pivot
            td["raw_def"] = eff_pivot
        td["adj_off"] = td["raw_off"]
        td["adj_def"] = td["raw_def"]
        if td["poss_weight"] > 0:
            td["raw_t"] = (td["poss_sum"] + pace_pivot * 3.0) / (td["poss_weight"] + 3.0)
        else:
            td["raw_t"] = pace_pivot
        td["adj_t"] = td["raw_t"]

    # PASS 2: Gauss-Seidel Iterative Opponent Adjustment Loop (KenPom Eff + Tempo)
    box_teams = [td for td in teams.values() if td["poss_weight"] > 0]
    for iteration in range(30):
        max_delta = 0.0
        for td in teams.values():
            if td["weight_sum"] <= 0:
                continue

            # Bayesian Preseason/Prior Anchor: decays as games accumulate
            curr_g = td["curr_games"]
            w_prior = max(0.0, (10.0 - curr_g) * 0.5) if td["games"] < 10 else 0.0

            sum_adj_o = eff_pivot * w_prior
            sum_adj_d = eff_pivot * w_prior
            tot_w = w_prior

            for opp, off_eff, def_eff, w in td["schedule"]:
                if opp in teams:
                    opp_d = teams[opp]["adj_def"]
                    opp_o = teams[opp]["adj_off"]
                else:
                    opp_d = eff_pivot
                    opp_o = eff_pivot

                # KenPom opponent adjustment equations
                sum_adj_o += (off_eff + (eff_pivot - opp_d)) * w
                sum_adj_d += (def_eff + (eff_pivot - opp_o)) * w
                tot_w += w

            new_off = sum_adj_o / tot_w
            new_def = sum_adj_d / tot_w

            # Opponent-adjusted tempo: game_poss = (team_t + opp_t) / 2 => team_obs = 2*poss - opp_t
            new_t = td["adj_t"]
            if td["poss_weight"] > 0:
                w_prior_t = 4.0
                sum_adj_t = pace_pivot * w_prior_t
                tot_wt = w_prior_t
                for opp, poss, w in td["poss_schedule"]:
                    opp_t = teams[opp]["adj_t"] if opp in teams else pace_pivot
                    obs_t = 2.0 * poss - opp_t
                    sum_adj_t += obs_t * w
                    tot_wt += w
                new_t = max(pace_pivot - 12.0, min(pace_pivot + 12.0, sum_adj_t / tot_wt))

            delta = max(abs(new_off - td["adj_off"]), abs(new_def - td["adj_def"]), abs(new_t - td["adj_t"]))
            if delta > max_delta:
                max_delta = delta

            td["adj_off"] = new_off
            td["adj_def"] = new_def
            td["adj_t"] = new_t

        # Re-center distributions around pivots
        avg_o = sum(td["adj_off"] for td in teams.values()) / len(teams)
        avg_d = sum(td["adj_def"] for td in teams.values()) / len(teams)
        for td in teams.values():
            td["adj_off"] += (eff_pivot - avg_o)
            td["adj_def"] += (eff_pivot - avg_d)
        if box_teams:
            avg_t = sum(td["adj_t"] for td in box_teams) / len(box_teams)
            for td in box_teams:
                td["adj_t"] += (pace_pivot - avg_t)

        if max_delta < 0.005:
            break

    # PASS 3: Format output records with Four Factors
    output_stats = []
    for team_name, td in teams.items():
        w = td["weight_sum"]
        g = td["games"]
        if w < 0.5 or g < 1:
            continue

        std_dev_totals = 15.0
        n_totals = len(td["game_totals"])
        if n_totals > 1:
            mean_tot = sum(td["game_totals"]) / n_totals
            variance = sum((x - mean_tot) ** 2 for x in td["game_totals"]) / (n_totals - 1)
            std_dev_totals = round(math.sqrt(variance), 2)

        # Four Factors (if box score coverage available)
        ts_pct = None
        tov_rate = None
        orb_rate = None
        opp_ts_pct = None
        if td["box_weight"] >= 1.0:
            fga = max(td["fga"], 0.001)
            ofga = max(td["opp_fga"], 0.001)
            drb_opp = td["drb"] + td["opp_orb"]
            ts_denom = 2.0 * (fga + 0.44 * td["fta"])
            ts_pct = round(td["pts_for"] / ts_denom, 4) if ts_denom > 0 else None
            tov_rate = round(td["tov"] / fga, 4)
            orb_denom = td["orb"] + max(td["trb"] - td["orb"], 0.001)
            orb_rate = round(td["orb"] / orb_denom, 4) if orb_denom > 0 else None
            ots_denom = 2.0 * (ofga + 0.44 * td["opp_fta"])
            opp_ts_pct = round(td["opp_pts"] / ots_denom, 4) if ots_denom > 0 else None

        net_margin = round(td["adj_off"] - td["adj_def"], 2)

        # Strength of Schedule (SOS) calculation
        opp_w_sum = sum(w for opp, _, _, w in td["schedule"] if opp in teams)
        if opp_w_sum > 0:
            sos_opp_off = sum(teams[opp]["adj_off"] * w for opp, _, _, w in td["schedule"] if opp in teams) / opp_w_sum
            sos_opp_def = sum(teams[opp]["adj_def"] * w for opp, _, _, w in td["schedule"] if opp in teams) / opp_w_sum
            sos_net = round(sos_opp_off - sos_opp_def, 2)
        else:
            sos_opp_off = eff_pivot
            sos_opp_def = eff_pivot
            sos_net = 0.0

        output_stats.append({
            "team_name":   team_name,
            "team_id":     0,
            "adj_off":     round(td["adj_off"], 1),
            "adj_def":     round(td["adj_def"], 1),
            "adj_t":       round(td["adj_t"], 1),
            "std_dev_totals": std_dev_totals,
            "games_played": g,
            "wins":        td["wins"],
            "win_pct":     round(td["wins"] / g, 3) if g > 0 else 0.0,
            "srs_rating":  net_margin,
            "source":      "ADVANCED",
            # Strength of Schedule metrics
            "sos":         sos_net,
            "sos_opp_off": round(sos_opp_off, 1),
            "sos_opp_def": round(sos_opp_def, 1),
            # Expose efficiency metrics for display / audit
            "ts_pct":      ts_pct,
            "tov_rate":    tov_rate,
            "orb_rate":    orb_rate,
            "opp_ts_pct":  opp_ts_pct,
        })

    return output_stats


import re
import unicodedata

NOW = datetime.datetime.now()

def clean_team_name(text: str) -> str:
    """
    Universal team name normalizer for robust cross-source matching.
    Strips diacritics/accents via Unicode NFKD decomposition, bridges Latin character
    equivalents (e.g. Polish ł->l, Scandinavian ø->o, Slavic đ->d, German ß->ss),
    and strips punctuation/excess whitespace.
    """
    if not text:
        return ""
    t = unicodedata.normalize('NFKD', str(text))
    t = ''.join(c for c in t if not unicodedata.combining(c))
    t = (t.replace('ł', 'l').replace('Ł', 'L')
          .replace('ø', 'o').replace('Ø', 'O')
          .replace('đ', 'd').replace('Đ', 'D')
          .replace('ß', 'ss'))
    t = re.sub(r'[^a-zA-Z0-9\s]', ' ', t)
    return ' '.join(t.lower().split())

def parse_date(date_str):
    """Parse dates from multiple sources: YYYY-MM-DD (API), Dec 12, 2025 (Proballers), DD.MM. HH:MM (Flashscore)"""
    if not date_str: return datetime.datetime.min
    if date_str == "Unknown":
        return datetime.datetime.min
    try:
        # ISO format: YYYY-MM-DD...
        if "-" in date_str and len(date_str) >= 10:
            return datetime.datetime.strptime(date_str[:10], "%Y-%m-%d")
        # Proballers: "Dec 12, 2025" or "Jan 9, 2026"
        for fmt in ("%b %d, %Y", "%B %d, %Y"):
            try:
                return datetime.datetime.strptime(date_str.strip()[:15], fmt)
            except:
                pass
        # Flashscore: "DD.MM. HH:MM" - NO year, infer from context
        if "." in date_str:
            clean = re.sub(r'[^0-9.]', '', date_str.split()[0])
            parts = [p for p in clean.split('.') if p]
            if len(parts) >= 2:
                day, month = int(parts[0]), int(parts[1])
                # Historical Flashscore files only contain completed past games.
                # If the inferred date is today or in the future, it must be from the prior year.
                year = NOW.year
                candidate = datetime.datetime(year, month, day)
                if candidate >= NOW.replace(hour=0, minute=0, second=0, microsecond=0):
                    candidate = datetime.datetime(year - 1, month, day)
                return candidate
    except:
        pass
    return datetime.datetime.min

def process_leagues(target_league_id=None):
    print(f"\n===========================================================")
    print("  INITIALIZING [SRS] & [ADVANCED] MATH RANKING ENGINE")
    print(f"===========================================================")
    
    map_file = "data/league_slug_map.json"
    if not os.path.exists(map_file):
        print("Missing league_slug_map.json! Aborting Matrix Build.")
        return
        
    with open(map_file, encoding="utf-8") as f:
        slug_map = json.load(f)
        
    f_files = glob.glob("data/historical/flashscore_*.json")
    p_files = glob.glob("data/historical/proballers_*.json")
    a_files = glob.glob("data/historical/api_basketball_*.json")
    n_files = glob.glob("data/historical/nbl1_official_*.json")
    historical_files = f_files + p_files + a_files + n_files
    os.makedirs("data/team_stats", exist_ok=True)
    
    # League Aliases: Ensure specific IDs inherit data from related slugs/IDs
    # (e.g. Belgium Pro League 374 inherits from BNXT 368 and legacy 24)
    LEAGUE_ALIASES = {
        374: [368, 24],
        65:  [368]
    }
    
    season = datetime.datetime.now().year
    
    # Group games by league
    games_by_league = {}
    
    for hf in historical_files:
        basename = os.path.basename(hf) 
        slug = basename.replace("flashscore_", "").replace("proballers_", "").replace("api_basketball_", "").replace("nbl1_official_", "").replace(".json", "")
        
        if slug.isdigit():
            league_id = int(slug)
        else:
            league_id = slug_map.get(slug)
        if not league_id:
            league_id = slug_map.get(slug.replace("-", "_"))
            if not league_id:
                print(f"Skipping {slug} - mapping ID not found in league_slug_map.json.")
                continue
            
        try:
            with open(hf, encoding="utf-8") as f:
                data = json.load(f)
                
            games = data if isinstance(data, list) else data.get("games", [])
            if not games: continue
            
            if league_id not in games_by_league:
                games_by_league[league_id] = []
            games_by_league[league_id].extend(games)
            
            # Check if this ID should also contribute to an alias (e.g. 368 contributes to 374)
            for target_id, source_ids in LEAGUE_ALIASES.items():
                if league_id in source_ids:
                    if target_id not in games_by_league:
                        games_by_league[target_id] = []
                    games_by_league[target_id].extend(games)
        except Exception as e:
            print(f"Error reading {hf}: {e}")

    # Also ingest modern daily cache files (data/api_basketball_today_*.json)
    # These contain finalized scores that auto_update_historical.py may not have
    # processed yet, ensuring the SRS matrix is always fully up to date.
    d_files = glob.glob("data/api_basketball_today_*.json")
    for df in d_files:
        try:
            with open(df, encoding="utf-8") as f:
                day_data = json.load(f)
            for entry in day_data.get("leagues_summary", []):
                lid = entry.get("league_id")
                if not lid:
                    continue
                for g in entry.get("games", []):
                    hs = g.get("home_score")
                    as_ = g.get("away_score")
                    if hs is None or as_ is None:
                        continue
                    try:
                        hs = int(hs)
                        as_ = int(as_)
                    except (TypeError, ValueError):
                        continue
                    # Skip awarded/forfeited matches — not real game totals
                    if g.get("status") == "Game Awarded":
                        continue
                    if hs == 0 and as_ == 0:
                        continue
                    if g.get("status") not in ("Game Finished", "Final", "AOT", "FT") and hs == 0 and as_ == 0:
                        continue
                    clean = {
                        "date": str(g.get("time", "") or day_data.get("date", ""))[:10],
                        "home_team": g.get("home", ""),
                        "away_team": g.get("away", ""),
                        "home_score": hs,
                        "away_score": as_,
                        "game_id": f"daily_{g.get('home','')}_{g.get('away','')}_{hs}_{as_}"
                    }
                    if lid not in games_by_league:
                        games_by_league[lid] = []
                    games_by_league[lid].append(clean)
                    
                    # Also contribute to aliases
                    for target_id, source_ids in LEAGUE_ALIASES.items():
                        if lid in source_ids:
                            if target_id not in games_by_league:
                                games_by_league[target_id] = []
                            games_by_league[target_id].append(clean)
        except Exception as e:
            print(f"Error reading daily cache {df}: {e}")

    success_count = 0
    
    for league_id, all_games in games_by_league.items():
        league_id = re.sub(r'[^a-zA-Z0-9_-]', '', str(league_id))
        if target_league_id and str(league_id) != str(target_league_id):
            continue
        if len(all_games) < 5:
            continue
            
        # 1. Parse dates and filter invalid games
        valid_games = []
        for g in all_games:
            pd = parse_date(g.get("date", ""))
            if pd > datetime.datetime.min:
                g["_parsed_date"] = pd
                valid_games.append(g)

        # 1.5. Apply cross-source canonical name mapping BEFORE fuzzy normalization.
        # This ensures games labelled with API names get merged with Proballers games
        # under the canonical (Proballers) name, preventing duplicate ghost entries.
        for g in valid_games:
            if g.get("home_team") in CROSS_SOURCE_CANONICAL_MAP:
                g["home_team"] = CROSS_SOURCE_CANONICAL_MAP[g["home_team"]]
            if g.get("away_team") in CROSS_SOURCE_CANONICAL_MAP:
                g["away_team"] = CROSS_SOURCE_CANONICAL_MAP[g["away_team"]]

        # 2. Normalize team names across all data sources
        import difflib
        team_name_map = {}
        all_names = set()
        for g in valid_games:
            if g.get("home_team"): all_names.add(g.get("home_team"))
            if g.get("away_team"): all_names.add(g.get("away_team"))
            
        sorted_names = sorted(list(all_names), key=len, reverse=True)
        for name in sorted_names:
            matched = False
            clean_name = clean_team_name(name)
            for primary in set(team_name_map.values()):
                clean_pri = clean_team_name(primary)
                
                # Rule 1: Exact clean name equality (stripping diacritics/case/punctuation)
                if clean_name == clean_pri:
                    team_name_map[name] = primary
                    matched = True
                    break
                
                # Rule 2: High similarity via difflib, guarded against collapsing distinct schools (e.g. State, Tech, A&M, Baptist)
                diff_words = {'state', 'tech', 'am', 'city', 'college', 'university', 'north', 'south', 'east', 'west', 'northern', 'southern', 'eastern', 'western', 'central', 'w', 'women', 'baptist'}
                words1 = set(clean_name.split())
                words2 = set(clean_pri.split())
                if (words1 & diff_words) != (words2 & diff_words):
                    continue
                similarity = difflib.SequenceMatcher(None, clean_name, clean_pri).ratio()
                if similarity >= 0.92:
                    team_name_map[name] = primary
                    matched = True
                    break
                    
            if not matched:
                team_name_map[name] = name


        # Apply normalized names
        for g in valid_games:
            g["home_team"] = team_name_map.get(g.get("home_team"), g.get("home_team"))
            g["away_team"] = team_name_map.get(g.get("away_team"), g.get("away_team"))
            
        # Helper for matching teams during cross-source deduplication
        def _teams_match(t1, t2):
            if not t1 or not t2: return False
            if t1 == t2: return True
            c1 = clean_team_name(t1)
            c2 = clean_team_name(t2)
            if c1 == c2: return True
            if c1 in c2 or c2 in c1:
                diff_words = {'state', 'tech', 'am', 'city', 'college', 'university', 'north', 'south', 'east', 'west'}
                w1 = set(c1.split()) - diff_words
                w2 = set(c2.split()) - diff_words
                if w1 and w2 and (w1 & w2):
                    return True
            if difflib.SequenceMatcher(None, c1, c2).ratio() >= 0.75:
                return True
            return False

        # 3. Deduplicate using normalized identifiers + score-indexed cross-source tolerance
        unique_games = []
        score_index = {}
        exact_index = {}

        # Sort: prefer official API games with standard ISO dates (YYYY-MM-DD) first
        def _dedupe_sort_key(g):
            d_str = str(g.get("date", ""))
            is_iso = ("-" in d_str and len(d_str) >= 10)
            has_stats = bool(g.get("stats") or g.get("advanced_stats"))
            return (1 if is_iso else 0, 1 if has_stats else 0)

        valid_games.sort(key=_dedupe_sort_key, reverse=True)

        for g in valid_games:
            g_date = g["_parsed_date"]
            g_ht = g.get("home_team", "")
            g_at = g.get("away_team", "")
            g_hs = g.get("home_score")
            g_as = g.get("away_score")

            # 3a. Exact Date + Team match
            exact_key = f"{g_date.strftime('%Y-%m-%d')}_{g_ht}_{g_at}"
            if exact_key in exact_index:
                existing = exact_index[exact_key]
                new_adv = g.get("advanced_stats") or g.get("stats")
                old_adv = existing.get("advanced_stats") or existing.get("stats")
                if new_adv and not old_adv:
                    existing["stats"] = new_adv
                continue

            # 3b. Score + Near-Date (±2 days) tolerance match (e.g. Proballers US-ET vs API UTC)
            matched_existing = None
            if g_hs is not None and g_as is not None:
                try:
                    cand_list = score_index.get((int(g_hs), int(g_as)), [])
                    for ug in cand_list:
                        u_date = ug["_parsed_date"]
                        if abs((g_date - u_date).total_seconds()) <= 86400 * 2:
                            if _teams_match(g_ht, ug.get("home_team", "")) and _teams_match(g_at, ug.get("away_team", "")):
                                matched_existing = ug
                                break
                except (ValueError, TypeError):
                    pass

            if matched_existing:
                new_adv = g.get("advanced_stats") or g.get("stats")
                old_adv = matched_existing.get("advanced_stats") or matched_existing.get("stats")
                if new_adv and not old_adv:
                    matched_existing["stats"] = new_adv
            else:
                unique_games.append(g)
                exact_index[exact_key] = g
                if g_hs is not None and g_as is not None:
                    try:
                        score_key = (int(g_hs), int(g_as))
                        if score_key not in score_index:
                            score_index[score_key] = []
                        score_index[score_key].append(g)
                    except (ValueError, TypeError):
                        pass

        # 3c. Attach any unparsed/unknown date games by exact score + team match without duplicating
        for g in all_games:
            d_str = str(g.get("date", ""))
            if d_str == "Unknown" or not d_str:
                g_hs = g.get("home_score")
                g_as = g.get("away_score")
                if g_hs is not None and g_as is not None:
                    try:
                        cand_list = score_index.get((int(g_hs), int(g_as)), [])
                        for ug in cand_list:
                            if _teams_match(g.get("home_team", ""), ug.get("home_team", "")) and _teams_match(g.get("away_team", ""), ug.get("away_team", "")):
                                new_adv = g.get("advanced_stats") or g.get("stats")
                                old_adv = ug.get("advanced_stats") or ug.get("stats")
                                if new_adv and not old_adv:
                                    ug["stats"] = new_adv
                                break
                    except (ValueError, TypeError):
                        pass

        merged_games = unique_games
        
        # Sort by date for chronological math
        merged_games.sort(key=lambda x: x["_parsed_date"])
        
        # Hard Date Cutoff Filter
        now = datetime.datetime.now()
        cur_year = now.year
        cur_month = now.month
        
        summer_league_ids = {"13", "66", "76", "222", "207", "208", "209", "210", "211", "212", "213", "214", "215", "216"}
        lid_str = str(league_id)

        # Calendar-year summer leagues run within a single calendar year (e.g. WNBA, NBL1, CEBL).
        # Global winter leagues run across calendar year boundaries (e.g. Sept to May).
        is_calendar_year = (lid_str in summer_league_ids)

        if is_calendar_year:
            cutoff_date = datetime.datetime(cur_year, 1, 1)
        else:
            # Global Winter Leagues default
            if cur_month >= 8:
                cutoff_date = datetime.datetime(cur_year, 8, 1)
            else:
                cutoff_date = datetime.datetime(cur_year - 1, 8, 1)
                
        current_season_games = [g for g in merged_games if g["_parsed_date"] >= cutoff_date]
        # In early season (or autumn months for winter leagues), anchor with prior season
        is_early_season = (len(current_season_games) < 40) or (not is_calendar_year and cur_month in (8, 9, 10, 11)) or (league_id in (116, 423) and len(current_season_games) < 1000)

        # Build per-team current-season game count for UI display
        from collections import Counter as _Counter
        current_season_team_counts = _Counter()
        for _g in current_season_games:
            ht = _g.get("home_team")
            at = _g.get("away_team")
            if ht:
                current_season_team_counts[ht] += 1
                c_ht = CROSS_SOURCE_CANONICAL_MAP.get(ht)
                if c_ht and c_ht != ht:
                    current_season_team_counts[c_ht] += 1
            if at:
                current_season_team_counts[at] += 1
                c_at = CROSS_SOURCE_CANONICAL_MAP.get(at)
                if c_at and c_at != at:
                    current_season_team_counts[c_at] += 1

        def _resolve_season_games(t_name):
            if not t_name: return 0
            if t_name in current_season_team_counts:
                return current_season_team_counts[t_name]
            c_name = CROSS_SOURCE_CANONICAL_MAP.get(t_name)
            if c_name and c_name in current_season_team_counts:
                return current_season_team_counts[c_name]
            for k, v in CROSS_SOURCE_CANONICAL_MAP.items():
                if v == t_name and k in current_season_team_counts:
                    return current_season_team_counts[k]
            cln = clean_team_name(t_name)
            for k, cnt in current_season_team_counts.items():
                ck = clean_team_name(k)
                if cln == ck or (len(ck) >= 4 and (ck in cln or cln in ck)):
                    return cnt
            return 0

        if is_early_season:
            # Look back 365 days to anchor with the prior season
            prior_cutoff = cutoff_date - datetime.timedelta(days=365)
            filtered_games = [g for g in merged_games if g["_parsed_date"] >= prior_cutoff]
            for g in filtered_games:
                g["is_prior_season"] = (g["_parsed_date"] < cutoff_date)
        else:
            filtered_games = current_season_games
            for g in filtered_games:
                g["is_prior_season"] = False
            
        if len(filtered_games) < 5:
            continue

        # Detect Advanced Eligibility: check whether the proballers stats key is present
        # We check more broadly across all filtered games to avoid missing sparse coverage
        advanced_eligible = False
        adv_count = 0
        box_poss_list = []   # collect real possession counts for pivot derivation
        box_ppg_list = []    # collect per-team PPG for pivot derivation
        for g in filtered_games:
            stats_val = g.get("advanced_stats") or g.get("stats")
            if stats_val and isinstance(stats_val, dict) and len(stats_val) > 0:
                adv_count += 1
                # Collect real possession data for pivot derivation
                home_s = stats_val.get("home", {})
                away_s = stats_val.get("away", {})
                if home_s and away_s:
                    fga = home_s.get("FGA", 0) + away_s.get("FGA", 0)
                    fta = home_s.get("FTA", 0) + away_s.get("FTA", 0)
                    tov = home_s.get("TOV", 0) + away_s.get("TOV", 0)
                    orb = home_s.get("ORB", 0) + away_s.get("ORB", 0)
                    if fga > 0:
                        poss_g = 0.5 * (fga - orb + tov + 0.44 * fta)
                        if 40 <= poss_g <= 120:
                            box_poss_list.append(poss_g)
            hs = g.get("home_score", 0)
            as_ = g.get("away_score", 0)
            if hs > 0:
                box_ppg_list.append(hs)
            if as_ > 0:
                box_ppg_list.append(as_)
                
        # Require at least 5 games with advanced data across the whole dataset
        if adv_count >= 5:
            advanced_eligible = True
            model_flag = "[ADVANCED]"
        else:
            advanced_eligible = False
            model_flag = "[  SRS   ]"
            
        srs_teams = calculate_iterative_srs(filtered_games)
        
        config_path = f"configs/leagues_v2/{league_id}.json"
        pace_pivot = 76.0
        eff_pivot = 108.0
        if os.path.exists(config_path):
            try:
                with open(config_path, encoding="utf-8") as f:
                    cfg_data = json.load(f)
                    pace_pivot = cfg_data.get("pace_pivot", 76.0)
                    eff_pivot = cfg_data.get("eff_pivot", 108.0)
            except: pass
        
        # --- Derive actual pace/eff pivots from box-score data for ADV model ---
        # Instead of using config pivots (which may be US-centric defaults),
        # compute the real average possessions and efficiency from the data.
        # This ensures the KenPom opponent-adjustment operates in the correct scale.
        derived_pace_pivot = pace_pivot   # fallback to config
        derived_eff_pivot = eff_pivot     # fallback to config
        if advanced_eligible and len(box_poss_list) >= 5 and len(box_ppg_list) >= 10:
            derived_pace_pivot = round(sum(box_poss_list) / len(box_poss_list), 1)
            avg_ppg = sum(box_ppg_list) / len(box_ppg_list)
            derived_eff_pivot = round(avg_ppg / (derived_pace_pivot / 100.0), 1)
            if abs(derived_pace_pivot - pace_pivot) > 2.0:
                print(f"    📐 PIVOT DERIVATION: league {league_id} — config pace={pace_pivot}, actual pace={derived_pace_pivot}, derived eff={derived_eff_pivot} (was {eff_pivot})")
                
        output_stats = []
        for team_name, data in srs_teams.items():
            if data["games"] < 1: continue
            
            w = data.get("weight_sum", data["games"])
            if w <= 0.001: continue
            
            raw_off = data["pts_for"] / w
            raw_def = data["pts_against"] / w
            
            # FIX 3: Proportional SRS decomposition
            # Weight SRS credit based on each team's offensive vs defensive contribution
            # instead of naive 50/50 split
            total_contribution = raw_off + raw_def
            if total_contribution > 0 and data.get("srs", 0) != 0:
                off_share = raw_off / total_contribution
                true_ppg_o = raw_off + (data["srs"] * off_share)
                true_ppg_d = raw_def - (data["srs"] * (1 - off_share))
            else:
                true_ppg_o = raw_off
                true_ppg_d = raw_def
            
            adjO = round(true_ppg_o / (pace_pivot / 100), 1) if pace_pivot > 0 else 108.0
            adjD = round(true_ppg_d / (pace_pivot / 100), 1) if pace_pivot > 0 else 108.0
            
            win_pct = round(data["wins"] / data["games"], 3) if data["games"] > 0 else 0.0
            
            std_dev_totals = 15.0
            n_totals = len(data.get("game_totals", []))
            if n_totals > 1:
                mean_tot = sum(data["game_totals"]) / n_totals
                variance = sum((x - mean_tot) ** 2 for x in data["game_totals"]) / (n_totals - 1)
                import math
                std_dev_totals = round(math.sqrt(variance), 2)
            
            team_obj = {
                "team_name": team_name,
                "team_id": 0,
                "adj_off": adjO,
                "adj_def": adjD,
                "adj_t": round(pace_pivot, 1),
                "std_dev_totals": std_dev_totals,
                "games_played": data["games"],
                "current_season_games": _resolve_season_games(team_name),
                "wins": data["wins"],
                "win_pct": win_pct,
                "srs_rating": round(data["srs"], 2),
                "sos": round(data.get("sos", 0.0), 2)
            }
            
            if advanced_eligible:
                team_obj["efg_perc"] = None
                team_obj["to_perc"] = None
                team_obj["or_perc"] = None
                team_obj["ftr"] = None
                
            output_stats.append(team_obj)
            
        # Write [  SRS   ] Fallback unconditionally for all leagues
        payload_srs = {
            "league_id": league_id,
            "season": season,
            "model_architecture": "[  SRS   ]",
            "calculated_at": datetime.datetime.now().isoformat(),
            "teams": output_stats
        }
        with open(f"data/bball_stats_{league_id}_srs_v2.json", "w", encoding="utf-8") as f:
            json.dump(payload_srs, f, indent=4)

        if not is_early_season and len(output_stats) > 0:
            with open(f"data/bball_stats_{league_id}_prior_srs.json", "w", encoding="utf-8") as f:
                json.dump(payload_srs, f, indent=4)

        # Write [ADVANCED] — uses GENUINE KenPom-equivalent opponent-adjusted efficiency ratings
        # Uses derived pivots from actual box-score data instead of config defaults
        adv_stats = calculate_advanced_ratings(filtered_games, pace_pivot=derived_pace_pivot, eff_pivot=derived_eff_pivot) if advanced_eligible else []
        if adv_stats:
            for t in adv_stats:
                t["current_season_games"] = _resolve_season_games(t["team_name"])
            payload_adv = {
                "league_id": league_id,
                "season": season,
                "model_architecture": "[ADVANCED]",
                "derived_pace_pivot": derived_pace_pivot,
                "derived_eff_pivot": derived_eff_pivot,
                "calculated_at": datetime.datetime.now().isoformat(),
                "teams": adv_stats
            }
            with open(f"data/bball_stats_{league_id}_adv_v2.json", "w", encoding="utf-8") as f:
                json.dump(payload_adv, f, indent=4)
        else:
            # Not enough box-score games — fall back to SRS payload
            payload_adv_fb = dict(payload_srs)
            payload_adv_fb["model_architecture"] = "[ADVANCED]"
            payload_adv_fb["note"] = "Insufficient box-score coverage; using SRS fallback"
            with open(f"data/bball_stats_{league_id}_adv_v2.json", "w", encoding="utf-8") as f:
                json.dump(payload_adv_fb, f, indent=4)
            
        # --- ALGORITHMIC GHOST INJURY DETECTION ---
        if advanced_eligible:
            ghost_injuries = {}
            team_histories = {} 
            # chronologically ordered!
            sorted_games = sorted(filtered_games, key=lambda x: x.get("_parsed_date", datetime.datetime.min))
            
            for g in sorted_games:
                ht = g.get("home_team")
                at = g.get("away_team")
                h_s = g.get("stats", {}).get("home", {})
                a_s = g.get("stats", {}).get("away", {})
                
                for team, stats in [(ht, h_s), (at, a_s)]:
                    if team not in team_histories:
                        team_histories[team] = {"players": {}, "games_total": 0, "last_2_rosters": []}
                    
                    th = team_histories[team]
                    th["games_total"] += 1
                    
                    current_roster = set()
                    players = stats.get("players", [])
                    for p in players:
                        name = p.get("name")
                        pts = p.get("pts", 0)
                        if not name: continue
                        current_roster.add(name)
                        if name not in th["players"]:
                            th["players"][name] = {"games_played": 0, "total_pts": 0}
                        th["players"][name]["games_played"] += 1
                        th["players"][name]["total_pts"] += pts
                        
                    th["last_2_rosters"].append(current_roster)
                    if len(th["last_2_rosters"]) > 2:
                        th["last_2_rosters"].pop(0)
                        
            for team, th in team_histories.items():
                if th["games_total"] < 5: continue
                
                last_2_combined = set()
                for roster in th["last_2_rosters"]:
                    last_2_combined = last_2_combined.union(roster)
                    
                injuries = []
                for name, p in th["players"].items():
                    gp = max(p["games_played"], 1)
                    ppg = p["total_pts"] / gp
                    # Active rotational threshold (played in 30% of season)
                    if gp >= (th["games_total"] * 0.3):
                        if name not in last_2_combined:
                            # They missed the last 2 games!
                            if ppg >= 15.0:
                                injuries.append({"player": name, "note": f"{name} (Ghost Injury All-Star - {ppg:.1f} PPG)", "status": "Out", "impact": "all_star_out"})
                            elif ppg >= 10.0:
                                injuries.append({"player": name, "note": f"{name} (Ghost Injury Starter - {ppg:.1f} PPG)", "status": "Out", "impact": "starter_out"})
                            elif ppg >= 6.0:
                                injuries.append({"player": name, "note": f"{name} (Ghost Injury Bench - {ppg:.1f} PPG)", "status": "Out", "impact": "bench_out"})
                                
                if injuries:
                    ghost_injuries[team] = injuries
                    
            with open(f"data/ghost_injuries_{league_id}.json", "w", encoding="utf-8") as f:
                json.dump(ghost_injuries, f, indent=4)
                
        success_count += 1

    print(f"Generated Proprietary Predictive Mathematical Matrices for exactly {success_count} global leagues.")
    print(f"===========================================================")

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--league_id", type=str, default=None, help="Process single league ID")
    args = parser.parse_args()
    process_leagues(target_league_id=args.league_id)
