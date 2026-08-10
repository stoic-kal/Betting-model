import SwiftUI

struct AccountView:View{
    @EnvironmentObject var settings:AppSettings;@State private var draftURL="";@State private var saved=false
    var body:some View{NavigationStack{ZStack{AppTheme.background.ignoresSafeArea();Form{Section("Research preferences"){HStack{Text("Unit reference");Spacer();TextField("20",value:$settings.unitValue,format:.number).keyboardType(.decimalPad).multilineTextAlignment(.trailing).frame(width:90)};Text("Used only to illustrate historical tracking. It does not place or recommend a wager.").font(.caption).foregroundStyle(AppTheme.muted)}
        Section("Data connection"){TextField("Backend URL",text:$draftURL).textInputAutocapitalization(.never).autocorrectionDisabled();Button(saved ? "Saved":"Save backend address"){settings.backendURL=draftURL.trimmingCharacters(in:.whitespacesAndNewlines);saved=true};Text("Simulator default: http://127.0.0.1:3000\nA physical iPhone requires your Mac’s network address or a hosted HTTPS API.").font(.caption).foregroundStyle(AppTheme.muted)}
        Section("Subscription"){HStack{VStack(alignment:.leading){Text("Private research access").font(.headline);Text("StoreKit subscriptions will be added after the public track record and TestFlight validation.").font(.caption).foregroundStyle(AppTheme.muted)};Spacer();Text("COMING LATER").font(.caption2.bold()).foregroundStyle(AppTheme.gold)}}
        Section("Responsible use"){Text("Jingleez Picks provides sports analytics and model-generated predictions for informational and entertainment purposes only. We do not accept, facilitate or place wagers. Nothing presented guarantees results or constitutes financial advice.");Text("This service is intended for adults who meet the legal age requirements in their jurisdiction.");Link("Call 1-800-GAMBLER",destination:URL(string:"tel:18004262537")!).foregroundStyle(AppTheme.gold)}
        Section("Product promises"){Label("No wagers or deposits",systemImage:"checkmark.shield.fill");Label("No sportsbook credentials",systemImage:"checkmark.shield.fill");Label("Immutable pregame predictions",systemImage:"checkmark.shield.fill");Label("Wins and losses remain visible",systemImage:"checkmark.shield.fill")}
    }.scrollContentBackground(.hidden).background(AppTheme.background).navigationTitle("Account")}.onAppear{draftURL=settings.backendURL}}
}
}
