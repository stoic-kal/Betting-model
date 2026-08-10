import Foundation

struct SlateResponse: Decodable { let date: String; let picks: [Pick]; let count: Int }
struct MobileSlateResponse:Decodable { let date:String;let games:[MobileGame];let count:Int }
struct MobileGame:Decodable,Identifiable {
    var id:Int{gamePK};let gamePK:Int;let date,matchup,awayTeam,homeTeam,awayAbbr,homeAbbr:String
    let awayTeamID,homeTeamID:Int;let awayPitcher,homePitcher:String?;let awayPitcherID,homePitcherID:Int?
    let venue,time,status,scheduledStart:String?;let picks:[Pick];let officialLocked:Bool
    enum CodingKeys:String,CodingKey{case gamePK="game_pk",date,matchup,awayTeam="away_team",homeTeam="home_team",awayAbbr="away_abbr",homeAbbr="home_abbr",awayTeamID="away_team_id",homeTeamID="home_team_id",awayPitcher="away_pitcher",homePitcher="home_pitcher",awayPitcherID="away_pitcher_id",homePitcherID="home_pitcher_id",venue,time,status,scheduledStart="scheduled_start",picks,officialLocked="official_locked"}
}
struct Pick: Decodable, Identifiable {
    var id: String { gameID + pickType }; let gameID,date,matchup,pickType,pick:String; let odds:Double
    let openingOdds,closingOdds,clv,modelProb,ev:Double?; let status,modelVersion,modelBuild,forecastStage,scheduledStart:String?
    let kellyUnits,expectedRuns,marketTotal:Double?; let completeness:Completeness?
    enum CodingKeys:String,CodingKey { case gameID="game_id",date,matchup,pickType="pick_type",pick,odds,openingOdds="opening_odds",closingOdds="closing_odds",clv,modelProb="model_prob",ev,status,modelVersion="model_version",modelBuild="model_build",forecastStage="forecast_stage",scheduledStart="scheduled_start",kellyUnits="kelly_units",expectedRuns="expected_runs",marketTotal="market_total",completeness }
}
struct Completeness:Decodable { let present,total:Int;let missing:[String];var complete:Bool{total>0&&present==total} }
struct RecordResponse:Decodable { let summary:RecordSummary;let rows:[RecordRow] }
struct RecordSummary:Decodable { let resolved,wins,losses:Int;let winRate,profit,roi,avgClv:Double?;enum CodingKeys:String,CodingKey{case resolved,wins,losses,profit,roi;case winRate="win_rate",avgClv="avg_clv"} }
struct RecordRow:Decodable,Identifiable { let id:Int;let date,game,type,pick,status:String;let modelProb,openingOdds,closingOdds,clv,ev,kellyUnits,profit:Double?;enum CodingKeys:String,CodingKey{case id,date,game,type,pick,clv,ev,status,profit;case modelProb="model_prob",openingOdds="opening_odds",closingOdds="closing_odds",kellyUnits="kelly_units"} }
struct LossReviewResponse:Decodable { let summary:LossSummary;let warnings:[String];let byType,byDirection,probabilityBuckets:[PerformanceBucket];enum CodingKeys:String,CodingKey{case summary,warnings;case byType="by_type",byDirection="by_direction",probabilityBuckets="probability_buckets"} }
struct LossSummary:Decodable { let resolved,wins,losses:Int;let winRate,avgWinClv,avgLossClv:Double?;let largeTotalMisses:Int;enum CodingKeys:String,CodingKey{case resolved,wins,losses;case winRate="win_rate",avgWinClv="avg_win_clv",avgLossClv="avg_loss_clv",largeTotalMisses="large_total_misses"} }
struct PerformanceBucket:Decodable,Identifiable { var id:String{label};let label:String;let n,wins,losses:Int;let winRate:Double?;enum CodingKeys:String,CodingKey{case label,n,wins,losses;case winRate="win_rate"} }
