async function generatePicks() {
    try {
        const res = await fetch('/api/run-picks', {method: 'POST', headers: {'X-Requested-With': 'Jingleez'}});
        const data = await res.json();
        
        if (data.status === 'error') {
            showMessage('❌ ERROR: ' + data.message);
            return;
        }
        
        showMessage('✅ PICKS LOADED!');
        
        // Store all data globally
        window.allData = data;
        
        // Group moneyline by game
        const mlByGame = {};
        data.moneyline_all.forEach((pick) => {
            if (!mlByGame[pick.matchup]) {
                mlByGame[pick.matchup] = [];
            }
            mlByGame[pick.matchup].push(pick);
        });
        
        // Render moneyline
        let mlHtml = '';
        Object.entries(mlByGame).forEach(([matchup, picks]) => {
            mlHtml += `
                <div class="game-card">
                    <div class="game-header">
                        <div class="matchup">${matchup}</div>
                        <div class="date">${picks[0].date}</div>
                    </div>
                    <div class="game-picks">
                        ${picks.map(pick => `
                            <div class="pick-item ${pick.has_edge ? 'edge' : 'no-edge'}" onclick="showGameDetails('${pick.matchup.replace(/'/g, "\\'")}', '${pick.date}')">
                                <div class="pick-type">${pick.pick}</div>
                                <div class="pick-prob">${pick.model_prob}</div>
                                <div class="pick-prob">@ ${pick.odds}</div>
                                <div class="pick-ev ${pick.ev_value > 0 ? 'ev-positive' : 'ev-negative'}">${pick.ev}</div>
                            </div>
                        `).join('')}
                    </div>
                </div>
            `;
        });
        
        document.getElementById('ml-container').innerHTML = mlHtml;
        document.getElementById('ml-stats').textContent = 
            `TOTAL GAMES: ${Object.keys(mlByGame).length} | PICKS WITH EDGE: ${data.ml_count}`;
        
        // Group totals by game
        const totByGame = {};
        data.totals_all.forEach((pick) => {
            if (!totByGame[pick.matchup]) {
                totByGame[pick.matchup] = [];
            }
            totByGame[pick.matchup].push(pick);
        });
        
        // Render totals
        let totHtml = '';
        Object.entries(totByGame).forEach(([matchup, picks]) => {
            totHtml += `
                <div class="game-card">
                    <div class="game-header">
                        <div class="matchup">${matchup}</div>
                        <div class="date">${picks[0].date}</div>
                    </div>
                    <div class="game-picks">
                        ${picks.map(pick => `
                            <div class="pick-item ${pick.has_edge ? 'edge' : 'no-edge'}" onclick="showGameDetails('${pick.matchup.replace(/'/g, "\\'")}', '${pick.date}', true)">
                                <div class="pick-type">${pick.pick}</div>
                                <div class="pick-prob">Expected: ${pick.expected_runs}</div>
                                <div class="pick-prob">${pick.model_prob}</div>
                                <div class="pick-prob">@ ${pick.odds}</div>
                                <div class="pick-ev ${pick.ev_value > 0 ? 'ev-positive' : 'ev-negative'}">${pick.ev}</div>
                            </div>
                        `).join('')}
                    </div>
                </div>
            `;
        });
        
        document.getElementById('tot-container').innerHTML = totHtml;
        document.getElementById('tot-stats').textContent = 
            `TOTAL GAMES: ${Object.keys(totByGame).length} | PICKS WITH EDGE: ${data.totals_count}`;
        
    } catch (e) {
        showMessage('❌ ERROR: ' + e.message);
    }
}

async function showGameDetails(matchup, date, isTotals) {
    const modal = document.getElementById('gameModal');
    document.getElementById('modalTitle').textContent = matchup;
    
    console.log('Fetching details for:', matchup, 'on', date);
    
    try {
        const res = await fetch(`/api/game-details?matchup=${encodeURIComponent(matchup)}&date=${date}`);
        const details = await res.json();
        
        console.log('Details response:', details);
        
        if (details.status === 'success') {
            document.getElementById('modalStadium').textContent = 
                details.stadium.stadium + (details.stadium.city ? ` - ${details.stadium.city}` : '');
            document.getElementById('modalHomePitcher').textContent = details.pitchers.home_pitcher;
            document.getElementById('modalAwayPitcher').textContent = details.pitchers.away_pitcher;
            document.getElementById('modalTemp').textContent = details.weather.temp;
            document.getElementById('modalWind').textContent = details.weather.wind;
        }
    } catch (e) {
        console.error('Fetch error:', e);
    }
    
    modal.classList.add('active');
}

function closeModal() {
    document.getElementById('gameModal').classList.remove('active');
}

window.onclick = function(event) {
    const modal = document.getElementById('gameModal');
    if (event.target === modal) {
        modal.classList.remove('active');
    }
}

function showMessage(msg) {
    const div = document.getElementById('message');
    div.innerHTML = `<div class="nes-container is-rounded" style="margin-bottom: 20px; padding: 10px; font-size: 10px;">${msg}</div>`;
}
