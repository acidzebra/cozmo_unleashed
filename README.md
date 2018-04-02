# cozmo_unleashed

Attempting to create a perpetuum cozmobile

This is a script to turn cozmo into an autonomous desk toy. He will play until his battery runs low, then attempt to find and dock with his charger. If he succeeds he will wait until fully charged, then come out to play again.

He will not offer any block-related  games (yet), just do basic stuff like building pyramids, popping wheelies, singing songs, and stacking blocks. If he sees a face he recognises he might ask for a fistbump or request a game of peekaboo.

As he plays his "needs levels" (internal counters for repair/mood/energy) will go down as his battery levels go down, this in turn will affect his mood and potential actions.

It also contains a basic scheduler that allows you to set allowed play times during weekdays and weekends. Whenever he's in allowed playtime there's a chance he will get off his charger and play.

