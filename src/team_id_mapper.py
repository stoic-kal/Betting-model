TEAM_NAME_TO_ID = {
"New York Yankees": 147,
"Boston Red Sox": 111,
"Tampa Bay Rays": 139,
"Baltimore Orioles": 110,
"Toronto Blue Jays": 141,
"Chicago White Sox": 145,
"Cleveland Guardians": 114,
"Detroit Tigers": 116,
"Kansas City Royals": 118,
"Minnesota Twins": 142,
"Houston Astros": 117,
"Los Angeles Angels": 108,
"Oakland Athletics": 133,
"Seattle Mariners": 136,
"Texas Rangers": 140,
"Atlanta Braves": 144,
"Miami Marlins": 146,
"New York Mets": 121,
"Philadelphia Phillies": 143,
"Washington Nationals": 120,
"Chicago Cubs": 112,
"Cincinnati Reds": 113,
"Milwaukee Brewers": 158,
"Pittsburgh Pirates": 134,
"St. Louis Cardinals": 138,
"Arizona Diamondbacks": 109,
"Colorado Rockies": 115,
"Los Angeles Dodgers": 119,
"San Diego Padres": 135,
"San Francisco Giants": 137,
}


def get_team_id(team_name):

    return TEAM_NAME_TO_ID.get(team_name, 147)
