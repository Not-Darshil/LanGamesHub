// Importing this module registers every game's UI component.
import { registerGame } from ".";
import { BattleshipGame } from "./battleship/BattleshipGame";
import { BusinessGame } from "./business/BusinessGame";
import { ChessGame } from "./chess/ChessGame";
import { LudoGame } from "./ludo/LudoGame";
import { SnakesGame } from "./snakes/SnakesGame";
import { TypingGame } from "./typing/TypingGame";
import { UnoGame } from "./uno/UnoGame";

registerGame("uno", UnoGame);
registerGame("snakes", SnakesGame);
registerGame("ludo", LudoGame);
registerGame("battleship", BattleshipGame);
registerGame("chess", ChessGame);
registerGame("typing", TypingGame);
registerGame("business", BusinessGame);
