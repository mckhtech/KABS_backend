import os
from django.core.management.base import BaseCommand
from django.conf import settings
from design_agent.services.catalog_ingestor import CatalogIngestor

class Command(BaseCommand):
    help = 'Ingest catalog data from files in catalog_data directory'

    def add_arguments(self, parser):
        parser.add_argument(
            '--file',
            type=str,
            help='Specific file to ingest (default: all files)'
        )
        parser.add_argument(
            '--reset',
            action='store_true',
            help='Reset ChromaDB before ingestion'
        )

    def handle(self, *args, **options):
        ingestor = CatalogIngestor()
        
        if options['reset']:
            self.stdout.write("Resetting ChromaDB collections...")
            # Add reset logic here if needed
        
        catalog_data_path = settings.CATALOG_DATA_PATH
        
        if not os.path.exists(catalog_data_path):
            self.stdout.write(
                self.style.ERROR(f'Catalog data directory not found: {catalog_data_path}')
            )
            return
        
        if options['file']:
            # Ingest specific file
            file_path = options['file']
            self.stdout.write(f"Ingesting file: {file_path}")
            
            result = ingestor.ingest_catalog_from_file(file_path)
            
            self.stdout.write(
                self.style.SUCCESS(
                    f"Processed {result['processed']} items with {result['errors']} errors"
                )
            )
        else:
            # Ingest all catalog items from database
            self.stdout.write("Bulk ingesting all catalog items from database...")
            
            result = ingestor.bulk_ingest_catalog()
            
            self.stdout.write(
                self.style.SUCCESS(
                    f"Bulk ingestion completed: {result['total_processed']} items processed, "
                    f"{result['errors']} errors, {result['success_rate']:.1f}% success rate"
                )
            )