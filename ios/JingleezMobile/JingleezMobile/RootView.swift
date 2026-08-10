import SwiftUI

struct RootView:View {
    init(){UITabBar.appearance().backgroundColor=UIColor(AppTheme.panel)}
    var body:some View{
        TabView{
            TodayView().tabItem{Label("Today",systemImage:"sparkles")}
            AlertsView().tabItem{Label("Alerts",systemImage:"bell.badge")}
            ResultsView().tabItem{Label("Results",systemImage:"chart.line.uptrend.xyaxis")}
            InsightsView().tabItem{Label("Insights",systemImage:"brain.head.profile")}
            AccountView().tabItem{Label("Account",systemImage:"person.crop.circle")}
        }.tint(AppTheme.gold).background(AppTheme.background)
    }
}
