"""Research-local, point-in-time transformations of already safe source columns."""


def apply_transforms(frame, names):
    frame=frame.copy(); added=[]
    for name in names or []:
        if name == "run_acceleration":
            for side in ("home","away"):
                column=f"{side}_runs_accel_5v10"
                frame[column]=frame[f"{side}_runs_5g"]-frame[f"{side}_runs_10g"]
                added.append(column)
        elif name == "market_form_interaction":
            frame["research_market_form_interaction"]=(frame.market_home_probability-.5)*frame.home_form_edge
            added.append("research_market_form_interaction")
        else:
            raise ValueError(f"Unknown research feature transform: {name}")
    return frame,added
