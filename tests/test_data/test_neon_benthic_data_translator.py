import pytest
from nmdc_runtime.site.translation.neon_benthic_translator import (
    NeonBenthicDataTranslator,
)
import pandas as pd

from linkml_runtime.dumpers import json_dumper
from nmdc_runtime.util import validate_json
from tests.conftest import get_mongo_test_db

# Mock data for testing
benthic_data = {
    "mms_benthicMetagenomeSequencing": pd.DataFrame(
        [
            {
                "uid": "409b85ed-9f92-4948-a29a-e1bbcad0a3bf",
                "domainID": "D13",
                "siteID": "WLOU",
                "namedLocation": "WLOU.AOS.reach",
                "collectDate": "2018-07-26T15:51Z",
                "laboratoryName": "Battelle Applied Genomics",
                "sequencingFacilityID": "Battelle Memorial Institute",
                "processedDate": "2019-03-01",
                "dnaSampleID": "WLOU.20180726.AMC.EPILITHON.1-DNA1",
                "dnaSampleCode": "",
                "internalLabID": "BMI_AquaticPlate6WellA5",
                "barcodeSequence": "",
                "instrument_model": "NextSeq550",
                "sequencingMethod": "Illumina",
                "investigation_type": "metagenome",
                "sequencingConcentration": 0.3,
                "labPrepMethod": "BMI_metagenomicsSequencingSOP_v3",
                "sequencingProtocol": "BMI_metagenomicsSequencingSOP_v3",
                "illuminaAdapterKit": "Kapa Dual Index Kit",
                "illuminaIndex1": "CGCTCATT",
                "illuminaIndex2": "ACGTCCTG",
                "sequencerRunID": "HWVWKBGX7",
                "qaqcStatus": "Pass",
                "sampleTotalReadNumber": 8809468,
                "sampleFilteredReadNumber": 2952793.0,
                "averageFilteredReadQuality": 34.1,
                "ambiguousBasesNumber": 10359.0,
                "ncbiProjectID": "PRJNA406976",
                "processedSeqFileName": "BMI_AquaticPlate6WellA5_mms.fastq.zip",
                "analyzedBy": "hZbYwvE98vBBnHMG2IzsBA==",
                "remarks": "",
                "dataQF": "",
            }
        ]
    ),
    "mms_benthicMetagenomeDnaExtraction": pd.DataFrame(
        [
            {
                "uid": "0110830f-3b71-4361-8f37-0747f2c29d95",
                "domainID": "D13",
                "siteID": "WLOU",
                "namedLocation": "WLOU.AOS.reach",
                "laboratoryName": "Battelle Applied Genomics",
                "collectDate": "2018-07-26T15:51Z",
                "processedDate": "2019-02-12",
                "genomicsSampleID": "WLOU.20180726.AMC.EPILITHON.1",
                "genomicsSampleCode": "B00000010911",
                "deprecatedVialID": "",
                "dnaSampleID": "WLOU.20180726.AMC.EPILITHON.1-DNA1",
                "dnaSampleCode": "",
                "internalLabID": "BMI_AquaticPlate6WellA5",
                "sequenceAnalysisType": "marker gene and metagenomics",
                "testMethod": "BMI_dnaExtractionSOP_v1",
                "sampleMaterial": "biofilm",
                "sampleMass": None,  # No value provided in the data for sampleMass
                "samplePercent": 100.0,
                "nucleicAcidConcentration": 4.7,
                "nucleicAcidQuantMethod": "Quantus",
                "nucleicAcidPurity": None,  # No value provided in the data for nucleicAcidPurity
                "nucleicAcidRange": None,  # No value provided in the data for nucleicAcidRange
                "dnaPooledStatus": "N",
                "qaqcStatus": "Pass",
                "dnaProcessedBy": "hZbYwvE98vCkIvnhsCYWaA==",
                "remarks": "",
                "dataQF": "",
            }
        ]
    ),
    "amb_fieldParent": pd.DataFrame(
        [
            {
                "uid": "7434ec98-d4f4-49ec-a670-73446abc57b8",
                "domainID": "D13",
                "siteID": "WLOU",
                "namedLocation": "WLOU.AOS.reach",
                "aquaticSiteType": "stream",
                "decimalLatitude": 39.891366,
                "decimalLongitude": -105.915395,
                "coordinateUncertainty": 1000.0,
                "elevation": 2908.0,
                "elevationUncertainty": 1000.0,
                "geodeticDatum": "WGS84",
                "collectDate": "2018-07-26T15:51Z",
                "eventID": "WLOU.20180726",
                "sampleID": "WLOU.20180726.AMC.EPILITHON.1",
                "sampleCode": "",
                "samplingImpractical": "",
                "habitatType": "riffle",
                "sampleNumber": 1,
                "aquMicrobeType": "epilithon",
                "aquMicrobeScrubArea": 0.000802,
                "samplingProtocolVersion": "NEON.DOC.003044vC",
                "substratumSizeClass": "cobble",
                "fieldSampleVolume": 125.0,
                "remarks": "",
                "collectedBy": "rlehrter@battelleecology.org",
                "recordedBy": "Jswenson@battelleecology.org",
                "archiveSampleCond": "",
                "archiveID": "WLOU.20180726.AMC.EPILITHON.1",
                "archiveSampleCode": "B00000010896",
                "archiveFilteredSampleVolume": 25.0,
                "geneticSampleCond": "",
                "geneticSampleID": "WLOU.20180726.AMC.EPILITHON.1",
                "geneticSampleCode": "B00000010911",
                "geneticFilteredSampleVolume": 25.0,
                "metagenomicSampleCond": "",
                "metagenomicsCollected": "",
                "metagenomicSampleID": "",
                "metagenomicSampleCode": "",
                "metagenomicFilteredSampleVolume": "",
                "sampleMaterial": "biofilm",
                "labSampleMedium": "filter",
                "dataQF": "",
            }
        ]
    ),
}


class TestNeonBenthicDataTranslator:
    @pytest.fixture
    def translator(self, test_minter):
        return NeonBenthicDataTranslator(benthic_data, id_minter=test_minter)

    def test_get_database(self, translator):
        database = translator.get_database()

        # verify lengths of all collections in database
        assert len(database.biosample_set) == 1
        assert len(database.extraction_set) == 1
        assert len(database.library_preparation_set) == 1
        assert len(database.omics_processing_set) == 1
        assert len(database.processed_sample_set) == 2

        # verify contents of biosample_set
        biosample_list = database.biosample_set
        expected_biosample_names = [
            "WLOU.20180726.AMC.EPILITHON.1",
        ]
        for biosample in biosample_list:
            actual_biosample_name = biosample["name"]
            assert actual_biosample_name in expected_biosample_names

        # verify contents of omics_processing_set
        omics_processing_list = database.omics_processing_set
        expected_omics_processing = [
            "Terrestrial soil microbial communities - WLOU.20180726.AMC.EPILITHON.1-DNA1"
        ]
        for omics_processing in omics_processing_list:
            actual_omics_processing = omics_processing["name"]
            assert actual_omics_processing in expected_omics_processing

        extraction_list = database.extraction_set
        library_preparation_list = database.library_preparation_set
        omics_processing_list = database.omics_processing_set

        biosample_id = [bsm["id"] for bsm in biosample_list]
        for extraction in extraction_list:
            extraction_input = extraction.has_input
            extraction_output = extraction.has_output
            assert extraction_input == biosample_id

            for lib_prep in library_preparation_list:
                lib_prep_input = lib_prep.has_input
                lib_prep_output = lib_prep.has_output
                assert lib_prep_input == extraction_output

                for omics_processing in omics_processing_list:
                    omics_processing_input = omics_processing.has_input
                    assert omics_processing_input == lib_prep_output

        mongo_db = get_mongo_test_db()
        validation_result = validate_json(json_dumper.to_dict(database), mongo_db)
        assert validation_result == {"result": "All Okay!"}
        