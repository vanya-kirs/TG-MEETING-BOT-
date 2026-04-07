"""
Google Sheets integration service for automatic data synchronization.
"""
import os
import gspread
from gspread.exceptions import APIError, SpreadsheetNotFound, WorksheetNotFound
from google.oauth2.service_account import Credentials
from typing import Optional, Dict, Any
import logging
import asyncio

logger = logging.getLogger(__name__)


class GoogleSheetsService:
    """Service for interacting with Google Sheets for trainer data management."""
    
    def __init__(self, spreadsheet_id: str):
        """
        Initialize Google Sheets service.
        
        Args:
            spreadsheet_id: ID of the Google Spreadsheet to work with
        """
        self.spreadsheet_id = spreadsheet_id
        self.client = None
        self.spreadsheet = None
        # Lock для синхронизации доступа к Google Sheets API
        # Предотвращает race condition при одновременных записях из разных процессов
        self._write_lock = asyncio.Lock()
        self._initialize_client()
    
    def _initialize_client(self):
        """Initialize Google Sheets client using service account."""
        try:
            service_account_path = os.getenv('GOOGLE_SERVICE_ACCOUNT_PATH')
            if not service_account_path:
                logger.warning("GOOGLE_SERVICE_ACCOUNT_PATH not set. Sheets integration disabled.")
                return
            
            creds = Credentials.from_service_account_file(
                service_account_path,
                scopes=['https://www.googleapis.com/auth/spreadsheets', 'https://www.googleapis.com/auth/drive']
            )
            self.client = gspread.authorize(creds)
            self.spreadsheet = self.client.open_by_key(self.spreadsheet_id)
            logger.info(f"Google Sheets client initialized for spreadsheet {self.spreadsheet_id}")
        except Exception as e:
            logger.error(f"Failed to initialize Google Sheets client: {e}")
            self.client = None
    
    def _get_worksheet(self, sheet_name: str):
        """Get worksheet by name."""
        if not self.spreadsheet:
            logger.warning("Google Sheets client not initialized")
            return None
        try:
            return self.spreadsheet.worksheet(sheet_name)
        except WorksheetNotFound:
            logger.error(f"Worksheet '{sheet_name}' not found")
            return None
        except Exception as e:
            logger.error(f"Error accessing worksheet '{sheet_name}': {e}")
            return None
    
    def find_user_row(self, worksheet, column_index: int, search_value: str) -> Optional[int]:
        """
        Find row number by searching in a specific column.
        
        Args:
            worksheet: Worksheet object
            column_index: Column index (1-based)
            search_value: Value to search for
            
        Returns:
            Row number (1-based) or None if not found
        """
        try:
            cell = worksheet.find(search_value, in_column=column_index)
            return cell.row
        except Exception:
            return None
    
    async def sync_user_registration(self, user_data: Dict[str, Any]) -> bool:
        """
        Sync user registration data to Google Sheets (Основные данные пользователей).
        
        Columns:
        - A: ФИО (Full Name)
        - B: Номер телефона (Phone)
        - C: Дата рождения (Birthday)
        - D: Дата начала работы (manual only)
        - E: Самозанятый/ИП (СЗ or ИП)
        - F: Резерв (manual only)
        - G: Email
        
        Args:
            user_data: Dictionary with keys: full_name, phone, birthday, employment_type
            
        Returns:
            True if successful, False otherwise
        """
        if not self.client:
            logger.warning("Sheets client not initialized, skipping sync")
            return False
        
        # Используем блокировку для предотвращения race condition
        async with self._write_lock:
            try:
                ws = self._get_worksheet('Основные данные пользователей')
                if not ws:
                    return False
                
                # Find if user already exists by full name
                row = self.find_user_row(ws, 1, user_data.get('full_name'))
                
                if row:
                    # Update existing row - columns A, B, C, E, G are script-editable
                    ws.update_cell(row, 1, user_data.get('full_name', ''))
                    ws.update_cell(row, 2, user_data.get('phone', ''))
                    ws.update_cell(row, 3, user_data.get('birthday', ''))
                    ws.update_cell(row, 5, user_data.get('employment_type', ''))  # Column E
                    ws.update_cell(row, 7, user_data.get('email', ''))  # Column G
                    logger.info(f"Updated row {row} in 'Основные данные пользователей' for user {user_data.get('full_name')}")
                else:
                    # Add new row - columns A, B, C, E, G (D/F manual)
                    # Используем явное указание всех 7 столбцов для предотвращения смещения
                    ws.append_row([
                        user_data.get('full_name', ''),
                        user_data.get('phone', ''),
                        user_data.get('birthday', ''),  # Column C - Дата рождения
                        '',  # Column D - manual only
                        user_data.get('employment_type', ''),  # Column E - СЗ or ИП
                        '',  # Column F - manual only
                        user_data.get('email', ''),  # Column G - Email
                    ])
                    logger.info(f"Added new row in 'Основные данные пользователей' for user {user_data.get('full_name')}")
                
                return True
            except Exception as e:
                logger.error(f"Error syncing user registration to Sheets: {e}")
                return False
    
    async def sync_trainer_medical(self, trainer_name: str, med_date: str) -> bool:
        """
        Sync medical book information to Медицинские записи.
        
        Columns:
        - A: Имя тренера
        - B: Даты медицинской книжки
        
        Args:
            trainer_name: Trainer's full name
            med_date: Medical book date
            
        Returns:
            True if successful, False otherwise
        """
        if not self.client:
            logger.warning("Sheets client not initialized, skipping sync")
            return False
        
        async with self._write_lock:
            try:
                ws = self._get_worksheet('Медицинские записи')
                if not ws:
                    return False
                
                # Find trainer by name (column A)
                row = self.find_user_row(ws, 1, trainer_name)
                
                if row:
                    # Update existing row - column B for medical date
                    ws.update_cell(row, 2, med_date)
                    logger.info(f"Updated medical date in 'Медицинские записи' for {trainer_name}")
                else:
                    # Add new row if trainer not found
                    ws.append_row([trainer_name, med_date])
                    logger.info(f"Added new medical record in 'Медицинские записи' for {trainer_name}")
                
                return True
            except Exception as e:
                logger.error(f"Error syncing medical data to Sheets: {e}")
                return False

    def fetch_medical_records(self) -> Optional[list[tuple[str, str]]]:
        """
        Fetch all rows from Медицинские записи (columns A - имя, B - даты).
        """
        if not self.client:
            logger.warning("Sheets client not initialized, cannot fetch medical records")
            return None
        try:
            ws = self._get_worksheet('Медицинские записи')
            if not ws:
                return None
            values = ws.get_all_values()
            records: list[tuple[str, str]] = []
            for row in values:
                if len(row) < 2:
                    continue
                name = (row[0] or '').strip()
                date_value = (row[1] or '').strip()
                if not name:
                    continue
                records.append((name, date_value))
            return records
        except Exception as e:
            logger.error(f"Error fetching medical records: {e}")
            return None
    
    async def sync_trainer_qualification(self, trainer_name: str, qual_date: str) -> bool:
        """
        Sync qualification information to Образование и квалификация.
        
        Columns:
        - A: Имя тренера
        - B: Даты повышения квалификации
        
        Args:
            trainer_name: Trainer's full name
            qual_date: Qualification date
            
        Returns:
            True if successful, False otherwise
        """
        if not self.client:
            logger.warning("Sheets client not initialized, skipping sync")
            return False
        
        async with self._write_lock:
            try:
                ws = self._get_worksheet('Образование и квалификация')
                if not ws:
                    return False
                
                # Find trainer by name (column A)
                row = self.find_user_row(ws, 1, trainer_name)
                
                if row:
                    # Update existing row - column B for qualification date
                    ws.update_cell(row, 2, qual_date)
                    logger.info(f"Updated qualification date in 'Образование и квалификация' for {trainer_name}")
                else:
                    # Add new row
                    ws.append_row([trainer_name, qual_date])
                    logger.info(f"Added new qualification record in 'Образование и квалификация' for {trainer_name}")
                
                return True
            except Exception as e:
                logger.error(f"Error syncing qualification data to Sheets: {e}")
                return False

    def fetch_qualification_records(self) -> Optional[list[tuple[str, str]]]:
        """
        Fetch all rows from Образование и квалификация (columns A - имя, B - даты).
        """
        if not self.client:
            logger.warning("Sheets client not initialized, cannot fetch qualification records")
            return None
        try:
            ws = self._get_worksheet('Образование и квалификация')
            if not ws:
                return None
            values = ws.get_all_values()
            records: list[tuple[str, str]] = []
            for row in values:
                if len(row) < 2:
                    continue
                name = (row[0] or '').strip()
                date_value = (row[1] or '').strip()
                if not name:
                    continue
                records.append((name, date_value))
            return records
        except Exception as e:
            logger.error(f"Error fetching qualification records: {e}")
            return None
    
    def fetch_user_emails(self) -> Optional[list[tuple[str, str]]]:
        """
        Fetch all rows from Основные данные пользователей (columns A - ФИО, G - email).
        Returns list of tuples (full_name, email).
        """
        if not self.client:
            logger.warning("Sheets client not initialized, cannot fetch user emails")
            return None
        try:
            ws = self._get_worksheet('Основные данные пользователей')
            if not ws:
                return None
            values = ws.get_all_values()
            records: list[tuple[str, str]] = []
            for row in values:
                if len(row) < 7:
                    continue
                full_name = (row[0] or '').strip()
                email = (row[6] or '').strip() if len(row) > 6 else ''  # Column G (index 6)
                if not full_name:
                    continue
                records.append((full_name, email))
            return records
        except Exception as e:
            logger.error(f"Error fetching user emails: {e}")
            return None
    
    async def sync_user_to_lockers(self, full_name: str) -> bool:
        """
        Sync user name to Шкафчики sheet (column A).
        
        Args:
            full_name: User's full name
            
        Returns:
            True if successful, False otherwise
        """
        if not self.client:
            logger.warning("Sheets client not initialized, skipping sync")
            return False
        
        async with self._write_lock:
            try:
                ws = self._get_worksheet('Шкафчики')
                if not ws:
                    return False
                
                # Check if user already exists
                row = self.find_user_row(ws, 1, full_name)
                
                if not row:
                    # Add new row with only column A (ФИО)
                    ws.append_row([full_name])
                    logger.info(f"Added user to 'Шкафчики' sheet: {full_name}")
                
                return True
            except Exception as e:
                logger.error(f"Error syncing user to lockers sheet: {e}")
                return False
    
    async def sync_user_to_forms(self, full_name: str) -> bool:
        """
        Sync user name to Формы sheet (column A).
        
        Args:
            full_name: User's full name
            
        Returns:
            True if successful, False otherwise
        """
        if not self.client:
            logger.warning("Sheets client not initialized, skipping sync")
            return False
        
        async with self._write_lock:
            try:
                ws = self._get_worksheet('Формы')
                if not ws:
                    return False
                
                # Check if user already exists
                row = self.find_user_row(ws, 1, full_name)
                
                if not row:
                    # Add new row with only column A (ФИО)
                    ws.append_row([full_name])
                    logger.info(f"Added user to 'Формы' sheet: {full_name}")
                
                return True
            except Exception as e:
                logger.error(f"Error syncing user to forms sheet: {e}")
                return False
    
    async def sync_user_name_to_all_sheets(self, full_name: str) -> bool:
        """
        Add user name (ФИО) to column A in ALL sheets if not already present.
        Used during user registration.
        
        Args:
            full_name: User's full name (ФИО)
            
        Returns:
            True if successful, False otherwise
        """
        if not self.client:
            logger.warning("Sheets client not initialized, skipping sync")
            return False
        
        # Используем блокировку для предотвращения race condition
        async with self._write_lock:
            all_sheets = [
                'Основные данные пользователей',
                'Образование и квалификация',
                'Медицинские записи',
                'Шкафчики'
            ]
            
            success_count = 0
            
            for sheet_name in all_sheets:
                try:
                    ws = self._get_worksheet(sheet_name)
                    if not ws:
                        continue
                    
                    # Check if user already exists in column A
                    row = self.find_user_row(ws, 1, full_name)
                    
                    if not row:
                        # Add new row with only column A (ФИО)
                        ws.append_row([full_name])
                        logger.info(f"Added ФИО to '{sheet_name}': {full_name}")
                        success_count += 1
                except Exception as e:
                    logger.error(f"Error adding ФИО to '{sheet_name}': {e}")
            
            return success_count > 0
    
    async def update_user_name(self, old_name: str, new_name: str) -> bool:
        """
        Update user name across all sheets where it appears.
        
        Args:
            old_name: Old full name
            new_name: New full name
            
        Returns:
            True if successful, False otherwise
        """
        if not self.client:
            logger.warning("Sheets client not initialized, skipping sync")
            return False
        
        async with self._write_lock:
            updated = False
            
            # List of all sheets where user name might appear
            sheets_to_update = [
                'Основные данные пользователей',
                'Образование и квалификация',
                'Медицинские записи',
                'Шкафчики'
            ]
            
            for sheet_name in sheets_to_update:
                try:
                    ws = self._get_worksheet(sheet_name)
                    if not ws:
                        continue
                    
                    # Find row with old name in column A
                    row = self.find_user_row(ws, 1, old_name)
                    
                    if row:
                        ws.update_cell(row, 1, new_name)
                        logger.info(f"Updated name in '{sheet_name}': {old_name} -> {new_name}")
                        updated = True
                except Exception as e:
                    logger.error(f"Error updating name in '{sheet_name}': {e}")
            
            return updated
    
    async def update_user_employment_type(self, full_name: str, employment_type: str) -> bool:
        """
        Update employment type (СЗ/ИП) in Основные данные пользователей sheet.
        
        Args:
            full_name: User's full name
            employment_type: Employment type (СЗ or ИП)
            
        Returns:
            True if successful, False otherwise
        """
        if not self.client:
            logger.warning("Sheets client not initialized, skipping sync")
            return False
        
        async with self._write_lock:
            try:
                ws = self._get_worksheet('Основные данные пользователей')
                if not ws:
                    return False
                
                # Find row with user name in column A
                row = self.find_user_row(ws, 1, full_name)
                
                if row:
                    # Update column E (employment type)
                    ws.update_cell(row, 5, employment_type)
                    logger.info(f"Updated employment type in 'Основные данные пользователей' for {full_name}: {employment_type}")
                    return True
                else:
                    logger.warning(f"User {full_name} not found in 'Основные данные пользователей'")
                    return False
            except Exception as e:
                logger.error(f"Error updating employment type in Sheets: {e}")
                return False
    
    async def update_user_email(self, full_name: str, email: str) -> bool:
        """
        Update email in Основные данные пользователей sheet (column G).

        Args:
            full_name: User's full name
            email: Email address

        Returns:
            True if successful, False otherwise
        """
        if not self.client:
            logger.warning("Sheets client not initialized, skipping sync")
            return False

        async with self._write_lock:
            try:
                ws = self._get_worksheet('Основные данные пользователей')
                if not ws:
                    return False

                row = self.find_user_row(ws, 1, full_name)
                if row:
                    ws.update_cell(row, 7, email or '')
                    logger.info(f"Updated email in 'Основные данные пользователей' for {full_name}")
                    return True
                else:
                    logger.warning(f"User {full_name} not found in 'Основные данные пользователей'")
                    return False
            except Exception as e:
                logger.error(f"Error updating email in Sheets: {e}")
                return False

    def delete_trainer_from_sheets(self, trainer_name: str) -> bool:
        """
        Delete trainer from ALL sheets where they appear.
        
        Args:
            trainer_name: Trainer's full name
            
        Returns:
            True if successful, False otherwise
        """
        if not self.client:
            logger.warning("Sheets client not initialized, skipping sync")
            return False
        
        deleted = False
        
        # ALL sheets where trainer/user data might appear
        sheets_to_delete = [
            'Основные данные пользователей',
            'Образование и квалификация',
            'Медицинские записи',
            'Шкафчики'
        ]
        
        for sheet_name in sheets_to_delete:
            try:
                ws = self._get_worksheet(sheet_name)
                if not ws:
                    continue
                
                # Find row with trainer name in column A
                row = self.find_user_row(ws, 1, trainer_name)
                
                if row:
                    ws.delete_rows(row)
                    logger.info(f"Deleted trainer from '{sheet_name}': {trainer_name}")
                    deleted = True
            except Exception as e:
                logger.error(f"Error deleting trainer from '{sheet_name}': {e}")
        
        return deleted
    
    def is_available(self) -> bool:
        """Check if Google Sheets service is available."""
        return self.client is not None

