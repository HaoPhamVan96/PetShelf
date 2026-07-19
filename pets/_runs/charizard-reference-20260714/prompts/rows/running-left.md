Create one horizontal animation strip for Codex pet `charizard`, state `running-left`.

Use the attached canonical base for identity. Use the attached layout guide only for slot count, spacing, centering, and padding; do not draw the guide.

Output exactly 8 full-body frames in one left-to-right row on flat pure blue #0000FF. Treat the row as 8 invisible equal-width slots: one centered complete pose per slot, evenly spaced, with no overlap, clipping, empty slots, labels, or borders.

Identity: same pet in every frame: Faithfully match the supplied reference: a stocky, dark-orange Charizard with a very large pale cream belly, dark brown chest/shoulder mass, long thick tail curled left, blackish teal wing membranes, white claws, horned head, and a signature attached crown of intense orange-yellow flames flowing from shoulders/back plus a tail flame. Keep the flame mass visibly attached to the body, not floating. Full body, portrait-like strong stance, no trainer, no logo or text.. Preserve silhouette, face, proportions, markings, palette, material, style, and props.
Style: Pet-safe sprite: compact full-body mascot, readable in a 192x208 cell, clear silhouette, simple face, stable palette/materials, and crisp edges for chroma-key extraction. Style `flat-vector`: Flat vector-style mascot with simple geometric forms, crisp color areas, clean outline, and minimal shading. User style notes: Clean sharp cel-shaded illustrated Pokémon style. Preserve the dramatic high-contrast fiery silhouette and anatomy of the supplied art. Flat solid magenta chroma background only..
Animation continuity: keep apparent pet scale and baseline stable within the row unless the state itself intentionally changes vertical position, such as `jumping`. Move the pose within the slot instead of redrawing the pet larger or smaller frame to frame.

State action: Dragging-left flight loop: fly toward screen-left with wingbeats and a hovering body; legs are tucked and never walk.

State requirements:
- Show directional leftward flight through wingbeats, a hovering torso, tucked legs, and attached tail/flame movement only.
- The row must unmistakably face and travel left.
- The wingbeat cadence must visibly alternate across the 8 frames instead of repeating one nearly static pose.
- Do not draw speed lines, dust clouds, floor shadows, motion trails, or detached motion effects.

Clean extraction: crisp opaque edges, safe padding, no scenery, text, guide marks, checkerboard, shadows, glows, motion blur, speed lines, dust, detached effects, stray pixels, or chroma-key colors inside the pet.
