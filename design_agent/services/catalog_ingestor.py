import os
import logging
import chromadb
from chromadb.config import Settings
from typing import List, Dict, Any, Optional
from django.conf import settings
from ..models import CatalogItem, RuleChunk

logger = logging.getLogger('design_agent')

class CatalogIngestor:
    """Manage ChromaDB ingestion and querying for catalog items and rules"""
    
    def __init__(self):
        self.client = chromadb.PersistentClient(
            path=settings.CHROMADB_PATH,
            settings=Settings(allow_reset=True)
        )
        
        # Collections for different data types
        self.catalog_collection = self._get_or_create_collection("catalog_items")
        self.rules_collection = self._get_or_create_collection("design_rules")
        
        logger.info("ChromaDB client initialized")
    
    def _get_or_create_collection(self, name: str):
        """Get or create a ChromaDB collection"""
        try:
            collection = self.client.get_collection(name=name)
            logger.info(f"Retrieved existing collection: {name}")
        except ValueError:
            collection = self.client.create_collection(
                name=name,
                metadata={"hnsw:space": "cosine"}
            )
            logger.info(f"Created new collection: {name}")
        
        return collection
    
    def add_catalog_item(self, catalog_item: CatalogItem) -> bool:
        """Add single catalog item to ChromaDB"""
        try:
            # Prepare metadata
            metadata = {
                "sku": catalog_item.sku,
                "category": catalog_item.category,
                "name": catalog_item.name,
                "manufacturer": catalog_item.manufacturer or "",
                "base_price": float(catalog_item.base_price) if catalog_item.base_price else 0.0,
                "width": float(catalog_item.width) if catalog_item.width else 0.0,
                "height": float(catalog_item.height) if catalog_item.height else 0.0,
                "depth": float(catalog_item.depth) if catalog_item.depth else 0.0,
                "compatible_styles": ",".join(catalog_item.compatible_styles),
                "available_finishes": ",".join(catalog_item.available_finishes),
                "available_materials": ",".join(catalog_item.available_materials),
                "is_active": catalog_item.is_active
            }
            
            # Add to collection
            self.catalog_collection.add(
                documents=[catalog_item.embedding_text],
                metadatas=[metadata],
                ids=[str(catalog_item.id)]
            )
            
            logger.info(f"Added catalog item to ChromaDB: {catalog_item.sku}")
            return True
            
        except Exception as e:
            logger.error(f"Error adding catalog item {catalog_item.sku}: {str(e)}")
            return False
    
    def bulk_ingest_catalog(self, batch_size: int = 100) -> Dict[str, int]:
        """Bulk ingest all active catalog items"""
        try:
            # Clear existing catalog items
            self.catalog_collection.delete()
            self.catalog_collection = self._get_or_create_collection("catalog_items")
            
            catalog_items = CatalogItem.objects.filter(is_active=True)
            total_items = catalog_items.count()
            processed = 0
            errors = 0
            
            # Process in batches
            for i in range(0, total_items, batch_size):
                batch = catalog_items[i:i + batch_size]
                batch_docs = []
                batch_metadata = []
                batch_ids = []
                
                for item in batch:
                    try:
                        metadata = {
                            "sku": item.sku,
                            "category": item.category,
                            "name": item.name,
                            "manufacturer": item.manufacturer or "",
                            "base_price": float(item.base_price) if item.base_price else 0.0,
                            "width": float(item.width) if item.width else 0.0,
                            "height": float(item.height) if item.height else 0.0,
                            "depth": float(item.depth) if item.depth else 0.0,
                            "compatible_styles": ",".join(item.compatible_styles),
                            "available_finishes": ",".join(item.available_finishes),
                            "available_materials": ",".join(item.available_materials),
                        }
                        
                        batch_docs.append(item.embedding_text)
                        batch_metadata.append(metadata)
                        batch_ids.append(str(item.id))
                        
                    except Exception as e:
                        logger.error(f"Error preparing item {item.sku}: {str(e)}")
                        errors += 1
                
                # Add batch to ChromaDB
                if batch_docs:
                    try:
                        self.catalog_collection.add(
                            documents=batch_docs,
                            metadatas=batch_metadata,
                            ids=batch_ids
                        )
                        processed += len(batch_docs)
                        logger.info(f"Processed batch {i//batch_size + 1}: {len(batch_docs)} items")
                        
                    except Exception as e:
                        logger.error(f"Batch ingestion error: {str(e)}")
                        errors += batch_size
            
            result = {
                'total_processed': processed,
                'errors': errors,
                'success_rate': (processed / (processed + errors)) * 100 if (processed + errors) > 0 else 0
            }
            
            logger.info(f"Bulk catalog ingestion completed: {result}")
            return result
            
        except Exception as e:
            logger.error(f"Bulk ingestion failed: {str(e)}")
            return {'total_processed': 0, 'errors': total_items, 'success_rate': 0}
    
    def search_catalog_items(self, query: str, room_type: str = None, 
                           style_preference: str = None, category_filter: List[str] = None,
                           max_results: int = 10) -> List[Dict[str, Any]]:
        """Search catalog items using semantic similarity"""
        try:
            # Build where clause for filtering
            where_clause = {"is_active": True}
            
            if category_filter:
                where_clause["category"] = {"$in": category_filter}
            
            # Perform search
            results = self.catalog_collection.query(
                query_texts=[query],
                n_results=max_results,
                where=where_clause,
                include=["documents", "metadatas", "distances"]
            )
            
            # Format results
            formatted_results = []
            if results['documents'] and results['documents'][0]:
                for i, doc in enumerate(results['documents'][0]):
                    metadata = results['metadatas'][0][i]
                    distance = results['distances'][0][i]
                    
                    # Apply additional filtering
                    if style_preference and metadata.get('compatible_styles'):
                        if style_preference not in metadata['compatible_styles']:
                            continue
                    
                    result_item = {
                        'id': results['ids'][0][i],
                        'sku': metadata['sku'],
                        'name': metadata['name'],
                        'category': metadata['category'],
                        'description': doc,
                        'manufacturer': metadata['manufacturer'],
                        'base_price': metadata['base_price'],
                        'dimensions': {
                            'width': metadata['width'],
                            'height': metadata['height'],
                            'depth': metadata['depth']
                        },
                        'compatible_styles': metadata['compatible_styles'].split(',') if metadata['compatible_styles'] else [],
                        'available_finishes': metadata['available_finishes'].split(',') if metadata['available_finishes'] else [],
                        'available_materials': metadata['available_materials'].split(',') if metadata['available_materials'] else [],
                        'relevance_score': 1 - distance,  # Convert distance to similarity
                        'search_context': {
                            'query': query,
                            'room_type': room_type,
                            'style_preference': style_preference
                        }
                    }
                    formatted_results.append(result_item)
            
            logger.info(f"Catalog search returned {len(formatted_results)} results for query: {query}")
            return formatted_results
            
        except Exception as e:
            logger.error(f"Catalog search error: {str(e)}")
            return []
    
    def add_rule_chunk(self, rule_chunk: RuleChunk) -> bool:
        """Add design rule to ChromaDB"""
        try:
            metadata = {
                "rule_type": rule_chunk.rule_type,
                "title": rule_chunk.title,
                "priority": rule_chunk.priority,
                "applicable_rooms": ",".join(rule_chunk.applicable_rooms),
                "applicable_categories": ",".join(rule_chunk.applicable_categories),
                "applicable_styles": ",".join(rule_chunk.applicable_styles),
                "source": rule_chunk.source or "",
                "is_active": rule_chunk.is_active
            }
            
            self.rules_collection.add(
                documents=[rule_chunk.content],
                metadatas=[metadata],
                ids=[str(rule_chunk.id)]
            )
            
            logger.info(f"Added rule to ChromaDB: {rule_chunk.title}")
            return True
            
        except Exception as e:
            logger.error(f"Error adding rule {rule_chunk.title}: {str(e)}")
            return False
    
    def search_design_rules(self, query: str, room_type: str = None, 
                           categories: List[str] = None, max_results: int = 5) -> List[Dict[str, Any]]:
        """Search design rules for context"""
        try:
            where_clause = {"is_active": True}
            
            if room_type:
                # This is a simplified filter - you might want more sophisticated filtering
                pass
            
            results = self.rules_collection.query(
                query_texts=[query],
                n_results=max_results,
                where=where_clause,
                include=["documents", "metadatas", "distances"]
            )
            
            formatted_results = []
            if results['documents'] and results['documents'][0]:
                for i, doc in enumerate(results['documents'][0]):
                    metadata = results['metadatas'][0][i]
                    distance = results['distances'][0][i]
                    
                    # Filter by room type if specified
                    if room_type and metadata.get('applicable_rooms'):
                        applicable_rooms = metadata['applicable_rooms'].split(',')
                        if room_type not in applicable_rooms and 'all' not in applicable_rooms:
                            continue
                    
                    result_item = {
                        'id': results['ids'][0][i],
                        'rule_type': metadata['rule_type'],
                        'title': metadata['title'],
                        'content': doc,
                        'priority': metadata['priority'],
                        'applicable_rooms': metadata['applicable_rooms'].split(',') if metadata['applicable_rooms'] else [],
                        'applicable_categories': metadata['applicable_categories'].split(',') if metadata['applicable_categories'] else [],
                        'applicable_styles': metadata['applicable_styles'].split(',') if metadata['applicable_styles'] else [],
                        'source': metadata['source'],
                        'relevance_score': 1 - distance
                    }
                    formatted_results.append(result_item)
            
            # Sort by priority and relevance
            formatted_results.sort(key=lambda x: (x['priority'], x['relevance_score']), reverse=True)
            
            logger.info(f"Rule search returned {len(formatted_results)} results")
            return formatted_results
            
        except Exception as e:
            logger.error(f"Rule search error: {str(e)}")
            return []
    
    def ingest_catalog_from_file(self, file_path: str) -> Dict[str, int]:
        """
        Ingest catalog data from file in catalog_data/ directory
        This method will be called when you add your catalog file
        """
        try:
            full_path = os.path.join(settings.CATALOG_DATA_PATH, file_path)
            
            if not os.path.exists(full_path):
                logger.error(f"Catalog file not found: {full_path}")
                return {'processed': 0, 'errors': 1}
            
            # This is a placeholder - implement based on your catalog file format
            # Could be CSV, JSON, PDF, etc.
            logger.info(f"Processing catalog file: {file_path}")
            
            # Example for CSV processing:
            if file_path.endswith('.csv'):
                return self._process_catalog_csv(full_path)
            elif file_path.endswith('.json'):
                return self._process_catalog_json(full_path)
            else:
                logger.error(f"Unsupported file format: {file_path}")
                return {'processed': 0, 'errors': 1}
                
        except Exception as e:
            logger.error(f"Error ingesting catalog file: {str(e)}")
            return {'processed': 0, 'errors': 1}
    
    def _process_catalog_csv(self, file_path: str) -> Dict[str, int]:
        """Process CSV catalog file"""
        import pandas as pd
        
        try:
            df = pd.read_csv(file_path)
            processed = 0
            errors = 0
            
            for _, row in df.iterrows():
                try:
                    # Create CatalogItem from CSV row
                    catalog_item = CatalogItem(
                        sku=row.get('sku', ''),
                        name=row.get('name', ''),
                        category=row.get('category', 'cabinet'),
                        description=row.get('description', ''),
                        width=row.get('width'),
                        height=row.get('height'),
                        depth=row.get('depth'),
                        base_price=row.get('base_price'),
                        manufacturer=row.get('manufacturer', ''),
                        compatible_styles=row.get('compatible_styles', '').split(',') if row.get('compatible_styles') else [],
                        available_finishes=row.get('available_finishes', '').split(',') if row.get('available_finishes') else [],
                        available_materials=row.get('available_materials', '').split(',') if row.get('available_materials') else []
                    )
                    
                    # Save to database
                    catalog_item.save()
                    
                    # Add to ChromaDB
                    if self.add_catalog_item(catalog_item):
                        processed += 1
                    else:
                        errors += 1
                        
                except Exception as e:
                    logger.error(f"Error processing row: {str(e)}")
                    errors += 1
            
            return {'processed': processed, 'errors': errors}
            
        except Exception as e:
            logger.error(f"Error processing CSV: {str(e)}")
            return {'processed': 0, 'errors': 1}
    
    def _process_catalog_json(self, file_path: str) -> Dict[str, int]:
        """Process JSON catalog file"""
        import json
        
        try:
            with open(file_path, 'r') as f:
                data = json.load(f)
            
            processed = 0
            errors = 0
            
            items = data if isinstance(data, list) else data.get('items', [])
            
            for item_data in items:
                try:
                    catalog_item = CatalogItem(
                        sku=item_data.get('sku', ''),
                        name=item_data.get('name', ''),
                        category=item_data.get('category', 'cabinet'),
                        description=item_data.get('description', ''),
                        width=item_data.get('width'),
                        height=item_data.get('height'),
                        depth=item_data.get('depth'),
                        base_price=item_data.get('base_price'),
                        manufacturer=item_data.get('manufacturer', ''),
                        compatible_styles=item_data.get('compatible_styles', []),
                        available_finishes=item_data.get('available_finishes', []),
                        available_materials=item_data.get('available_materials', [])
                    )
                    
                    catalog_item.save()
                    
                    if self.add_catalog_item(catalog_item):
                        processed += 1
                    else:
                        errors += 1
                        
                except Exception as e:
                    logger.error(f"Error processing item: {str(e)}")
                    errors += 1
            
            return {'processed': processed, 'errors': errors}
            
        except Exception as e:
            logger.error(f"Error processing JSON: {str(e)}")
            return {'processed': 0, 'errors': 1}
