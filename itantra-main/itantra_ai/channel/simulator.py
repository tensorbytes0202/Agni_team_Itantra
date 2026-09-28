import random
from typing import Tuple

class WeakChannelSimulator:
    """
    Simulates a low-bitrate, lossy radio transceiver channel.
    Supports 0%, 5%, 10%, 20%, 30% packet drop rates or bit flip corruption.
    """

    def __init__(self, loss_rate: float = 0.0, seed: int = 42):
        self.loss_rate = loss_rate
        random.seed(seed)

    def transmit(self, bit_stream: str) -> Tuple[str, bool]:
        """
        Simulates transmission over lossy link.
        Returns (received_bit_stream, is_delivered_successfully).
        """
        # Determine if packet is dropped entirely
        if random.random() < self.loss_rate:
            return "", False # Packet dropped
            
        # Determine bit corruption/flips if loss_rate > 0
        received_bits = list(bit_stream)
        for i in range(len(received_bits)):
            # Micro bit flip chance proportional to loss rate
            if random.random() < (self.loss_rate * 0.05):
                received_bits[i] = '1' if received_bits[i] == '0' else '0'
                
        return "".join(received_bits), True
