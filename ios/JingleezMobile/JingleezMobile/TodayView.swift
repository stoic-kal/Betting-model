import SwiftUI

@MainActor final class TodayViewModel:ObservableObject{
    @Published var response:MobileSlateResponse?;@Published var loading=false;@Published var error:String?
    func load(baseURL:String)async{loading=true;error=nil;defer{loading=false};do{response=try await APIClient(baseURL:baseURL).todaySlate()}catch{self.error=error.localizedDescription}}
}

struct TodayView:View{
    @EnvironmentObject var settings:AppSettings;@StateObject private var vm=TodayViewModel()
    private let columns=[GridItem(.adaptive(minimum:165),spacing:10)]
    var body:some View{NavigationStack{ZStack{AppTheme.background.ignoresSafeArea();ScrollView{VStack(spacing:14){statusHeader
        if vm.loading&&vm.response==nil{ProgressView("Loading today’s games…").tint(AppTheme.gold).padding(.top,80)}
        else if let error=vm.error{EmptyState(icon:"wifi.exclamationmark",title:"Couldn’t reach the model",message:error+"\n\nKeep app.py running and check the backend address in Account.")}
        else if let games=vm.response?.games,games.isEmpty{EmptyState(icon:"calendar.badge.clock",title:"No MLB games today",message:"The schedule will appear automatically when MLB publishes it.")}
        else{LazyVGrid(columns:columns,spacing:10){ForEach(vm.response?.games ?? []){game in NavigationLink(value:game.id){CompactGameCard(game:game)}.buttonStyle(.plain)}}}
    }.padding(14)}}.navigationTitle("Today’s Games").navigationDestination(for:Int.self){id in if let game=vm.response?.games.first(where:{$0.id==id}){GameDetailView(game:game)}}.toolbar{ToolbarItem(placement:.topBarTrailing){Button{Task{await vm.load(baseURL:settings.backendURL)}}label:{Image(systemName:"arrow.clockwise")}}}}.task{await vm.load(baseURL:settings.backendURL)}.refreshable{await vm.load(baseURL:settings.backendURL)}}
    private var statusHeader:some View{HStack{VStack(alignment:.leading,spacing:5){Text(vm.response?.date ?? "TODAY").font(.caption.weight(.bold)).foregroundStyle(AppTheme.gold);Text("MLB MODEL BOARD").font(.title3.bold());Text("Tap a game for full research").font(.caption).foregroundStyle(AppTheme.muted)};Spacer();Text("\(vm.response?.count ?? 0)\nGAMES").font(.caption.bold()).multilineTextAlignment(.center).padding(10).background(AppTheme.raised,in:RoundedRectangle(cornerRadius:12))}.panel()}
}

struct CompactGameCard:View{
    let game:MobileGame
    var body:some View{VStack(spacing:10){HStack{Text(game.time ?? "TBD").font(.caption2.bold()).foregroundStyle(AppTheme.muted);Spacer();Image(systemName:game.officialLocked ? "lock.fill":"clock").foregroundStyle(game.officialLocked ? AppTheme.green:AppTheme.gold)}
        teamRow(game.awayAbbr,game.awayTeamID);teamRow(game.homeAbbr,game.homeTeamID)
        Divider().overlay(Color.white.opacity(0.1));HStack{Text(game.officialLocked ? "OFFICIAL PICKS LOCKED":"WAITING FOR LINEUPS").font(.system(size:9,weight:.bold)).foregroundStyle(game.officialLocked ? AppTheme.green:AppTheme.gold);Spacer();Image(systemName:"chevron.right").font(.caption2).foregroundStyle(AppTheme.muted)}
    }.frame(maxWidth:.infinity,minHeight:132,alignment:.top).panel()}
    private func teamRow(_ abbr:String,_ id:Int)->some View{HStack(spacing:9){TeamLogo(teamID:id,size:28);Text(abbr).font(.headline);Spacer()}}
}

struct TeamLogo:View{
    let teamID:Int;var size:CGFloat=46
    var body:some View{AsyncImage(url:URL(string:"https://midfield.mlbstatic.com/v1/team/\(teamID)/spots/72")){phase in switch phase{case .success(let image):image.resizable().scaledToFit();case .failure:Image(systemName:"baseball.fill").resizable().scaledToFit().foregroundStyle(AppTheme.muted);default:ProgressView().tint(AppTheme.gold)}}.frame(width:size,height:size)}
}

struct PitcherPhoto:View{
    let playerID:Int?
    var body:some View{
        Group{
            if let playerID{
                AsyncImage(url:URL(string:"https://img.mlbstatic.com/mlb-photos/image/upload/w_640,q_auto:best/v1/people/\(playerID)/headshot/67/current")){phase in
                    switch phase{
                    case .success(let image):image.resizable().scaledToFill()
                    case .failure:placeholder
                    default:ProgressView().tint(AppTheme.gold)
                    }
                }
            }else{placeholder}
        }.frame(width:150,height:220).background(AppTheme.raised).clipShape(RoundedRectangle(cornerRadius:10))
    }
    private var placeholder:some View{Image(systemName:"person.crop.rectangle.fill").resizable().scaledToFit().padding(25).foregroundStyle(AppTheme.muted)}
}

struct GameDetailView:View{
    let game:MobileGame
    var body:some View{ZStack{AppTheme.background.ignoresSafeArea();ScrollView{VStack(spacing:16){matchupHeader;pitchers;lockStatus
        if game.picks.isEmpty{EmptyState(icon:"lock.open.fill",title:"Official picks not locked",message:"The model will permanently record one Moneyline and one Total after MLB confirms both starting lineups.")}else{VStack(spacing:12){ForEach(game.picks){PickRow(pick:$0)}}.panel()}
        VStack(alignment:.leading,spacing:10){Text("Game information").font(.headline);Label(game.venue ?? "Venue TBD",systemImage:"mappin.and.ellipse");Label(game.time ?? "Time TBD",systemImage:"clock");Label(game.status ?? "Scheduled",systemImage:"calendar")}.frame(maxWidth:.infinity,alignment:.leading).font(.subheadline).panel()
    }.padding(16)}}.navigationTitle("Game Overview").navigationBarTitleDisplayMode(.inline)}
    private var matchupHeader:some View{HStack{VStack(spacing:8){TeamLogo(teamID:game.awayTeamID,size:62);Text(game.awayAbbr).font(.title2.bold());Text("AWAY").font(.caption2).foregroundStyle(AppTheme.muted)};Spacer();VStack(spacing:4){Text("AT").font(.caption.bold()).foregroundStyle(AppTheme.gold);Text(game.time ?? "TBD").font(.caption2).multilineTextAlignment(.center)};Spacer();VStack(spacing:8){TeamLogo(teamID:game.homeTeamID,size:62);Text(game.homeAbbr).font(.title2.bold());Text("HOME").font(.caption2).foregroundStyle(AppTheme.muted)}}.panel()}
    private var pitchers:some View{VStack(alignment:.leading,spacing:12){Text("Probable starters").font(.headline);HStack(alignment:.top){pitcher(game.awayPitcher,game.awayPitcherID,game.awayAbbr);Spacer();pitcher(game.homePitcher,game.homePitcherID,game.homeAbbr)}}.panel()}
    private func pitcher(_ name:String?,_ id:Int?,_ team:String)->some View{VStack(spacing:7){PitcherPhoto(playerID:id);Text(name ?? "TBD").font(.caption.bold()).multilineTextAlignment(.center).lineLimit(2);Text(team).font(.caption2).foregroundStyle(AppTheme.muted)}.frame(width:150)}
    private var lockStatus:some View{HStack{Image(systemName:game.officialLocked ? "checkmark.seal.fill":"person.3.sequence.fill").font(.title2).foregroundStyle(game.officialLocked ? AppTheme.green:AppTheme.gold);VStack(alignment:.leading,spacing:4){Text(game.officialLocked ? "Official lineup lock complete":"Monitoring official lineups").font(.headline);Text(game.officialLocked ? "These selections are permanent and will not change.":"Nothing is recorded until both MLB batting orders are confirmed.").font(.caption).foregroundStyle(AppTheme.muted)};Spacer()}.panel()}
}

struct PickRow:View{
    let pick:Pick;@State private var showSummary=false
    private var qualifies:Bool{(pick.kellyUnits ?? 0)>0&&(pick.ev ?? 0)>0&&(pick.completeness?.complete ?? false)}
    var body:some View{VStack(alignment:.leading,spacing:11){HStack{Label(pick.pickType=="moneyline" ? "MONEYLINE":"TOTAL",systemImage:pick.pickType=="moneyline" ? "baseball":"scope").font(.caption.bold()).foregroundStyle(AppTheme.gold);Spacer();Text(qualifies ? "QUALIFYING RESEARCH":"MODEL LEAN").font(.caption2.bold()).foregroundStyle(qualifies ? AppTheme.green:AppTheme.muted)};Text(pick.pick).font(.title3.bold());HStack{MetricView(label:"Model",value:percent(pick.modelProb));MetricView(label:"EV",value:signed(pick.ev,"%"),tint:(pick.ev ?? 0)>=0 ? AppTheme.green:AppTheme.red);MetricView(label:"Weight",value:String(format:"%.2fu",pick.kellyUnits ?? 0))};Button("Why this pick?"){showSummary=true}.buttonStyle(.borderedProminent).tint(AppTheme.gold).foregroundStyle(.black)}.sheet(isPresented:$showSummary){PickSummaryView(pick:pick)}}
    private func percent(_ v:Double?)->String{v.map{String(format:"%.1f%%",$0*100)} ?? "—"};private func signed(_ v:Double?,_ suffix:String)->String{v.map{String(format:"%+.1f",$0)+suffix} ?? "—"}
}

struct PickSummaryView:View{
    @Environment(\.dismiss)var dismiss;let pick:Pick
    var body:some View{NavigationStack{ZStack{AppTheme.background.ignoresSafeArea();ScrollView{VStack(alignment:.leading,spacing:18){Text(pick.pick).font(.largeTitle.bold());Text(pick.matchup).foregroundStyle(AppTheme.muted);HStack{MetricView(label:"Model probability",value:pick.modelProb.map{String(format:"%.1f%%",$0*100)} ?? "—");MetricView(label:"Projected EV",value:pick.ev.map{String(format:"%+.1f%%",$0)} ?? "—",tint:AppTheme.green)}.panel();Text(summary).foregroundStyle(.white.opacity(0.82)).lineSpacing(5).panel();Label("No wager is placed or facilitated",systemImage:"hand.raised.fill").panel()}.padding(16)}}.toolbar{ToolbarItem(placement:.topBarTrailing){Button("Done"){dismiss()}}}}}
    private var summary:String{"The model selected \(pick.pick) with a projected probability of \(String(format:"%.1f%%",(pick.modelProb ?? 0)*100)) and estimated advantage of \(String(format:"%+.1f%%",pick.ev ?? 0)). This official selection was stored after both MLB starting lineups were confirmed. It is model research, not a guarantee or instruction to wager."}
}
