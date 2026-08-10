import unittest

import run


class MultiplayerFlowTests(unittest.TestCase):
    def setUp(self):
        self.saved_state = {
            "game_mode": run.game_mode,
            "temporizador_activo": run.temporizador_activo,
            "tiempo_restante": run.tiempo_restante,
            "respuesta_actual": run.respuesta_actual.copy(),
            "puntuaciones": run.puntuaciones.copy(),
            "respuestas": run.respuestas.copy(),
            "jugadores": run.jugadores_conectados.copy(),
        }
        run.game_mode = "guess_song"
        run.temporizador_activo = True
        run.respuesta_actual = {
            "titulo": "Título",
            "artista": "Artista",
            "completa": "Título - Artista",
        }
        run.puntuaciones.clear()
        run.respuestas.clear()
        run.jugadores_conectados.clear()
        self.ana = run.socketio.test_client(run.app)
        self.luis = run.socketio.test_client(run.app)

    def tearDown(self):
        self.ana.disconnect()
        self.luis.disconnect()
        run.game_mode = self.saved_state["game_mode"]
        run.temporizador_activo = self.saved_state["temporizador_activo"]
        run.tiempo_restante = self.saved_state["tiempo_restante"]
        run.respuesta_actual = self.saved_state["respuesta_actual"]
        run.puntuaciones.clear()
        run.puntuaciones.update(self.saved_state["puntuaciones"])
        run.respuestas.clear()
        run.respuestas.update(self.saved_state["respuestas"])
        run.jugadores_conectados.clear()
        run.jugadores_conectados.update(self.saved_state["jugadores"])

    def test_two_players_receive_scores_and_shared_ranking(self):
        self.ana.emit("registrar", "ana")
        self.luis.emit("registrar", "luis")
        self.ana.get_received()
        self.luis.get_received()

        self.ana.emit("respuesta", {"nombre": "ana", "respuesta": "Título Artista"})
        self.luis.emit("respuesta", {"nombre": "luis", "respuesta": "Nada"})
        run.evaluar_respuestas()

        ana_events = self.ana.get_received()
        luis_events = self.luis.get_received()
        self.assertTrue(any(event["name"] == "resultado" for event in ana_events))
        self.assertTrue(any(event["name"] == "resultado" for event in luis_events))
        self.assertEqual(run.puntuaciones["ana"], 4)
        self.assertEqual(run.puntuaciones["luis"], 0)
        self.assertEqual(run.panel_ranking_data, [("ana", 4), ("luis", 0)])
