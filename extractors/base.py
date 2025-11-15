class BaseExtractor:
    KEYWORD = None

    def extract(self, order, client):
        raise NotImplementedError("Extractor must implement extract()")
