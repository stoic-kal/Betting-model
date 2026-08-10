import SwiftUI
import Charts

@MainActor final class ResultsViewModel:ObservableObject{@Published var data:RecordResponse?;@Published var error:String?;func load(_ url:String)async{do{data=try await APIClient(baseURL:url).records();error=nil}catch{self.error=error.localizedDescription}}}
struct ResultsView:View{
    @EnvironmentObject var settings:AppSettings;@StateObject private var vm=ResultsViewModel();@State private var filter="all"
    private var rows:[RecordRow]{(vm.data?.rows ?? []).filter{filter=="all"||$0.type==filter}}
    var body:some View{NavigationStack{ZStack{AppTheme.background.ignoresSafeArea();ScrollView{VStack(spacing:16){if let s=vm.data?.summary{HStack{MetricView(label:"Record",value:"\(s.wins)-\(s.losses)");MetricView(label:"Win rate",value:s.winRate.map{String(format:"%.1f%%",$0)} ?? "—");MetricView(label:"ROI",value:s.roi.map{String(format:"%+.1f%%",$0)} ?? "—",tint:(s.roi ?? 0)>=0 ? AppTheme.green:AppTheme.red)}.panel()}
        Picker("Market",selection:$filter){Text("All").tag("all");Text("Moneyline").tag("moneyline");Text("Totals").tag("totals")}.pickerStyle(.segmented)
        if rows.isEmpty{EmptyState(icon:"clock.arrow.circlepath",title:"No resolved history",message:vm.error ?? "Results appear after picks are automatically graded.")}else{LazyVStack(spacing:10){ForEach(rows){ResultRow(row:$0)}}}
    }.padding(16)}}.navigationTitle("Transparent Results")}.task{await vm.load(settings.backendURL)}.refreshable{await vm.load(settings.backendURL)}}
}
struct ResultRow:View{let row:RecordRow;var body:some View{HStack(spacing:12){Image(systemName:row.status=="won" ? "checkmark.circle.fill":row.status=="lost" ? "xmark.circle.fill":"clock.fill").font(.title2).foregroundStyle(row.status=="won" ? AppTheme.green:row.status=="lost" ? AppTheme.red:AppTheme.gold);VStack(alignment:.leading,spacing:4){Text(row.pick).font(.subheadline.bold());Text(row.game).font(.caption2).foregroundStyle(AppTheme.muted);Text("\(row.date) · \(row.type.uppercased())").font(.caption2).foregroundStyle(AppTheme.muted)};Spacer();VStack(alignment:.trailing,spacing:4){Text(row.status.uppercased()).font(.caption.bold());Text(row.profit.map{String(format:"%+.2f",$0)} ?? "—").foregroundStyle((row.profit ?? 0)>=0 ? AppTheme.green:AppTheme.red);Text(row.clv.map{String(format:"CLV %+.2fpp",$0)} ?? "CLV —").font(.caption2).foregroundStyle(AppTheme.muted)}}.panel()}}
