UPDATE markets
SET category = 'sports'
WHERE LOWER(CONCAT_WS(' ', title, slug, event_slug, description)) REGEXP
    'esports|e-sports|e sports|电竞|电子竞技|counter-strike|counter strike|cs2|csgo|valorant|dota|league of legends|overwatch|starcraft|bo3|bo5|iem |major stage|natus vincere| navi | g2 |faze|vitality|over/under| o/u ';
